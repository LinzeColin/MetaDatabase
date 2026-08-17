r"""卡住的同步必须被推进终态，不能永远转圈（2026-08-17）。

## 它修的是什么

Owner 说「同步依旧不能使用」。从生产读回来的实况：

    xiaohongshu 09:58:32  status=scanning  evidence={"waiting_for_batch": true}
    bilibili    09:59:29  status=scanning  evidence={"waiting_for_batch": true}
    douyin      09:59:04  status=partial   BROWSER_SCAN_FAILED

前两个一个多小时没动，而 `status` 一直是非终态 —— 界面据此显示
「正在同步，请稍候」，于是**永远转圈**。

**检测早就有了**：`stalled_active_runs` 的 docstring 明写着它抓的正是
「点了同步永远在转」那种，`failure_copy` 里 `SYNC_STALLED` 的文案和
`[ 重试 ]` 动作也都写好了。缺的是**没有任何东西把看见的结果落成状态**：
它只被挂在 `/v1/status` 的审计里记一笔。

这是这个仓最贵的那个形状：灯装好了、判据也绿，而没有人接上开关。
（「判据没有调用方就不算做完」「注释声称的守卫不是守卫」）

## 口径

不新造判定：门槛与状态集合直接复用 `stalled_active_runs`。
终态选 `partial` 不是 `failed` —— 已取到的内容都还在，下次能续着跑，
这也正是 SYNC_STALLED 那句文案说的意思。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from social_archive.db import RuntimeStore  # noqa: E402


def _store(tmp_path: Path) -> RuntimeStore:
    store = RuntimeStore(tmp_path / "db.sqlite3")
    store.initialize()
    return store


def _make_run(store: RuntimeStore, *, platform: str, status: str, ago_seconds: int) -> str:
    """造一个「N 秒前更新过、状态是 status」的 run。

    直接写库：走产品路径造不出「一小时没动」这种状态，而那正是要测的东西。
    """
    import sqlite3  # noqa: PLC0415

    run_id = f"sync_{platform}_{status}_{ago_seconds}"
    with store.connection() as con:
        columns = {row[1] for row in con.execute("PRAGMA table_info(sync_run)")}
        assert "status" in columns and "updated_at" in columns, (
            f"sync_run 的列变了，这条夹具要跟着改：{sorted(columns)}")
        owner = store._ensure_owner_user(con, "2026-08-17T00:00:00Z")
        # sync_run.source_account_id 上有外键，先把账号那行建出来。
        con.execute(
            "INSERT OR IGNORE INTO source_account(id,user_id,platform,created_at,updated_at) "
            "VALUES(?,?,?,datetime('now'),datetime('now'))",
            (f"acct_{platform}", owner, platform),
        )
        try:
            con.execute(
                "INSERT INTO sync_run"
                "(id,user_id,source_account_id,platform,mode,status,started_at,updated_at) "
                "VALUES(?,?,?,?,?,?,datetime('now',?),datetime('now',?))",
                (run_id, owner, f"acct_{platform}", platform, "first_full", status,
                 f"-{ago_seconds + 60} seconds", f"-{ago_seconds} seconds"),
            )
        except sqlite3.IntegrityError as error:  # 列有 NOT NULL 就把夹具补齐再报
            raise AssertionError(f"造夹具失败（sync_run 有必填列？）：{error}") from error
    return run_id


def _status(store: RuntimeStore, run_id: str) -> tuple[str, str | None]:
    with store.connection() as con:
        row = con.execute(
            "SELECT status,last_error_code FROM sync_run WHERE id=?", (run_id,)
        ).fetchone()
    return (str(row["status"]), row["last_error_code"])


def test_卡了很久的同步会被判成终态(tmp_path: Path) -> None:
    store = _store(tmp_path)
    run_id = _make_run(store, platform="bilibili", status="scanning", ago_seconds=3600)

    assert _status(store, run_id)[0] == "scanning", "夹具没造对"
    reaped = store.fail_stalled_runs(stale_after_seconds=1800)

    assert reaped == 1, f"卡了一小时的 run 没被处置：reaped={reaped}"
    status, code = _status(store, run_id)
    assert status == "partial", f"还停在 {status}——界面会继续显示「正在同步，请稍候」"
    assert code == "SYNC_STALLED", f"没写失败码，用户看不到为什么：{code}"


def test_刚开始跑的不许被误杀(tmp_path: Path) -> None:
    """**反方向**。少了它，把实现写成「见到非终态就判死」也能让上面那条过，
    而那会把每一次正常同步在开跑三秒后就掐掉。"""
    store = _store(tmp_path)
    run_id = _make_run(store, platform="douyin", status="scanning", ago_seconds=10)

    assert store.fail_stalled_runs(stale_after_seconds=1800) == 0, "刚开始跑的被误杀了"
    assert _status(store, run_id)[0] == "scanning"


def test_已经结束的不再动它(tmp_path: Path) -> None:
    """终态的 run 不许被重写——重写会把真正的失败码盖掉，
    而那个码正是用户看到的那句话的来源。"""
    store = _store(tmp_path)
    run_id = _make_run(store, platform="xiaohongshu", status="partial", ago_seconds=86400)

    assert store.fail_stalled_runs(stale_after_seconds=1800) == 0
    assert _status(store, run_id)[0] == "partial"


def test_处置的口径和检测的口径是同一个(tmp_path: Path) -> None:
    """**不许各自一套。**

    这个仓撞过「两件判据看同一批文本而口径不同」。这里让两个函数
    对同一批数据表态：检测说有几个，处置就该动几个，一个不多一个不少。
    """
    store = _store(tmp_path)
    old_one = _make_run(store, platform="bilibili", status="scanning", ago_seconds=7200)
    _make_run(store, platform="douyin", status="scanning", ago_seconds=5)
    _make_run(store, platform="reddit", status="completed", ago_seconds=99999)

    seen = store.stalled_active_runs(stale_after_seconds=1800)
    assert [str(row["id"]) for row in seen] == [old_one], (
        f"检测到的不是预期那一个：{[row['id'] for row in seen]}")

    reaped = store.fail_stalled_runs(stale_after_seconds=1800)
    assert reaped == len(seen), f"检测说 {len(seen)} 个，处置了 {reaped} 个"
    # 处置完之后，检测应该看不到它了——否则每分钟都会重复处置一遍。
    assert store.stalled_active_runs(stale_after_seconds=1800) == [], (
        "处置完还在被检测到，worker 会每分钟重复写一次同一条")


def test_后台循环真的会调它() -> None:
    """**第三层：函数存在 ≠ 有人调。**

    这道判据纪念的缺陷正是「检测写好了、挂在审计里、没人处置」。
    如果只测上面四条，把 `fail_stalled_runs` 从 worker 里删掉，
    它们照样全绿，而用户那边照旧永远转圈。

    剥掉注释再查——说明里提到函数名不等于代码调了它。
    """
    import ast  # noqa: PLC0415

    source = (ROOT / "src/social_archive/worker.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "fail_stalled_runs" in called, (
        "worker.py 里没有任何一处**调用** fail_stalled_runs——"
        "卡住的同步不会被推进终态，界面继续永远转圈。\n"
        "（注释里写着不算：这道判据用 ast 查调用，不查字符串。）")
