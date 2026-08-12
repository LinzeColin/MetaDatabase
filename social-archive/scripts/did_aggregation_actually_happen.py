#!/usr/bin/env python3
r"""自动聚合在**他的生产库里**真的发生过吗（2026-08-13）。

## 为什么需要这个

他要的第一件事是「多平台聚合真的发生」。而这个仓验它的方式一直是**演练**：
在真 Chrome 里点一遍、看见条目进来、判据变绿。

演练证的是**按钮按得动**。它证不了**他那边发生过**。

这两件事分开过一次：8/3 那晚一条 SELECT 就看见真进了 260 条，
而 8/4 起因 `PLATFORM_PERMISSION_MISSING` 停了——**31 道门、1190 条测试
一处都没抓到**，因为门全在验机制，没有一个去问「后来还在跑吗」。

在这个脚本之前，仓里**没有任何东西读 `user_relation.last_sync_run_id`**。
也就是说「哪些条目是自动抓进来的」这个问题，谁都没问过。

## 它怎么答

只问三句能落到行上的话：

    1. 生产库里有过几次同步跑？分平台、分 mode/trigger、分 status。
    2. 有多少条收藏**是某一次跑带进来的**（`last_sync_run_id` 指得到一次真跑），
       多少条**没有任何一次跑认领**（手动存的、或更早的路子进来的）。
    3. 每个平台**最近一次成功的自动跑**是什么时候——「以前成过」和
       「现在还成」是两回事。

## 边界（写在这里，免得被读成别的）

- **只读，不写。** 库以 `mode=ro` 打开：路径写错会**报错**，而不是
  顺手建一个空库然后回「0 行」。这个仓踩过——`/var/lib/social-archive/
  social-archive.sqlite3` 那个 0 字节空壳就是这么来的，真库在 `runtime/` 里，
  **同名，差一层目录**。
- **0 不等于没问题。** 一次都没跑过会明说「**从来没发生过**」，
  不会印一个安静的 0 让人读成「没毛病」。
- **是播报，不是门。** 他还没连账号是完全正常的状态，不该让部署红。
  要当门用加 `--require-recent-success`，并且**必须自己给天数**——
  没有默认值，免得我替他选了一个宽松的口径。
- 印数一定连**分母和口径**：总行数、库文件大小、时间窗都印出来。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# **同名，差一层目录**：外面那个是我自己用错路径留下的 0 字节空壳。
RUNTIME_DB = Path("/var/lib/social-archive/runtime/social-archive.sqlite3")

AUTOMATIC_MODES = ("first_full", "incremental", "browser_import")
SUCCESS_STATUS = ("completed", "partial")


def _open_read_only(path: Path) -> sqlite3.Connection:
    """只读打开。**路径写错要炸，不许自动建库。**"""
    if not path.is_file():
        raise SystemExit(
            f"✗ 库不在这儿：{path}\n"
            f"  （别改成 sqlite3.connect(路径)——那个会把文件建出来，"
            f"然后一切读数都变成安静的 0。）")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(conn: sqlite3.Connection, sql: str, args: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone())


def collect(path: Path, recent_days: int | None) -> dict:
    conn = _open_read_only(path)
    try:
        for table in ("sync_run", "user_relation"):
            if not _table_exists(conn, table):
                raise SystemExit(f"✗ 库里没有 {table} 表：{path}")

        runs = _rows(conn, """
            SELECT platform, mode, trigger_type, status,
                   COUNT(*) AS runs,
                   SUM(imported_count)   AS imported,
                   SUM(discovered_count) AS discovered,
                   MAX(COALESCE(completed_at, updated_at)) AS latest_at
              FROM sync_run
             GROUP BY platform, mode, trigger_type, status
             ORDER BY latest_at DESC
        """)

        # **认领**：条目上记着的那次跑，在 sync_run 里得真找得到。
        # 只数「非空」会把指向已删除跑的孤儿算成有主。
        claimed = _rows(conn, """
            SELECT sr.platform,
                   sr.mode,
                   COUNT(DISTINCT ur.id) AS relations
              FROM user_relation ur
              JOIN sync_run sr ON sr.id = ur.last_sync_run_id
             GROUP BY sr.platform, sr.mode
             ORDER BY relations DESC
        """)
        totals = _rows(conn, """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN ur.last_sync_run_id IS NULL
                            OR ur.last_sync_run_id = '' THEN 1 ELSE 0 END) AS no_run_id,
                   SUM(CASE WHEN ur.last_sync_run_id IS NOT NULL
                            AND ur.last_sync_run_id <> ''
                            AND NOT EXISTS (SELECT 1 FROM sync_run s
                                             WHERE s.id = ur.last_sync_run_id)
                       THEN 1 ELSE 0 END) AS orphan_run_id
              FROM user_relation ur
        """)[0]

        # 每个平台最近一次**成功的自动**跑。「以前成过」和「现在还成」是两回事。
        qmarks_m = ",".join("?" * len(AUTOMATIC_MODES))
        qmarks_s = ",".join("?" * len(SUCCESS_STATUS))
        latest = _rows(conn, f"""
            SELECT platform,
                   MAX(COALESCE(completed_at, updated_at)) AS latest_success_at,
                   COUNT(*) AS successful_runs,
                   SUM(imported_count) AS imported
              FROM sync_run
             WHERE mode IN ({qmarks_m}) AND status IN ({qmarks_s})
             GROUP BY platform
             ORDER BY latest_success_at DESC
        """, AUTOMATIC_MODES + SUCCESS_STATUS)

        # 出错的那些：只给「最近一次」和它的错码，不整包倒出来。
        failures = _rows(conn, """
            SELECT platform, status, last_error_code,
                   COUNT(*) AS runs,
                   MAX(updated_at) AS latest_at
              FROM sync_run
             WHERE status NOT IN ('completed','partial')
             GROUP BY platform, status, last_error_code
             ORDER BY latest_at DESC
             LIMIT 12
        """)

        accounts = _rows(conn, """
            SELECT platform, connection_state, auto_sync_enabled,
                   last_sync_at, last_error_code, updated_at, created_at
              FROM source_account ORDER BY platform
        """) if _table_exists(conn, "source_account") else []
    finally:
        conn.close()

    claimed_total = sum(int(r["relations"] or 0) for r in claimed)
    total = int(totals["total"] or 0)
    ever = bool(latest)

    cutoff_note = None
    recent_ok = None
    if recent_days is not None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=recent_days))
        cutoff_s = cutoff.strftime("%Y-%m-%dT%H:%M:%S")
        cutoff_note = f"最近一次成功自动同步要晚于 {cutoff_s}Z（{recent_days} 天内）"
        recent_ok = any((r["latest_success_at"] or "") >= cutoff_s for r in latest)

    if not ever:
        message = ("**自动聚合在生产上从来没成功发生过**"
                   "（没有任何一次 mode∈自动 且 status∈成功 的跑）。")
    else:
        top = latest[0]
        message = (f"**发生过**：最近一次成功的自动同步是 {top['platform']} "
                   f"@ {top['latest_success_at']}；"
                   f"{total} 条收藏里 {claimed_total} 条能追到带它进来的那次跑。")

    return {
        "status": "PASS" if recent_ok is not False else "FAIL",
        "db": str(path),
        "db_bytes": path.stat().st_size,
        "aggregation_ever_succeeded": ever,
        "latest_successful_automatic_run_by_platform": latest,
        "runs_by_platform_mode_trigger_status": runs,
        "relations_claimed_by_a_run": claimed,
        "relation_totals": {
            "total_relations": total,
            "claimed_by_a_real_run": claimed_total,
            "no_run_id_at_all": int(totals["no_run_id"] or 0),
            "run_id_points_at_a_missing_run": int(totals["orphan_run_id"] or 0),
        },
        "recent_failures": failures,
        "accounts": accounts,
        "recent_window": cutoff_note,
        "recent_window_satisfied": recent_ok,
        "message_zh": message,
        "counting_convention": (
            "「自动」= mode∈" + "/".join(AUTOMATIC_MODES) +
            "，「成功」= status∈" + "/".join(SUCCESS_STATUS) +
            "；「被认领」= user_relation.last_sync_run_id 在 sync_run 里找得到，"
            "指向已不存在的跑单独计入 run_id_points_at_a_missing_run，不算认领。"),
        "what_this_does_not_prove": (
            "只说库里留下过什么。跑成功过不代表它现在还能跑成功，"
            "也不代表抓回来的内容是对的——那是别的判据的事。"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="自动聚合真的发生过吗")
    ap.add_argument("--db", default=str(RUNTIME_DB))
    ap.add_argument("--brief", action="store_true")
    ap.add_argument("--require-recent-success", type=int, default=None,
                    metavar="DAYS",
                    help="当门用：要求 DAYS 天内有过成功的自动同步。"
                         "**必须自己给天数**，没有默认值。")
    ap.add_argument("--host", default="",
                    help="给了就把自己送进那台机器的容器里跑（库只在容器里）")
    args = ap.parse_args()

    if args.host:
        import base64
        import shlex
        import subprocess
        blob = base64.b64encode(
            Path(__file__).read_text(encoding="utf-8").encode()).decode()
        # **argv 单独拼**：塞进 f-string 里要靠同引号嵌套，读起来像坏的。
        inner_argv = ["r"]
        if args.brief:
            inner_argv.append("--brief")
        if args.require_recent_success is not None:
            inner_argv += ["--require-recent-success",
                           str(args.require_recent_success)]
        inner = (f"import base64,sys;sys.argv={inner_argv!r};"
                 f"exec(base64.b64decode('{blob}'))")
        done = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=25", args.host,
             f"sudo docker exec social-archive-core-api-1 "
             f"python3 -c {shlex.quote(inner)}"],
            capture_output=True, text=True, timeout=180)
        sys.stdout.write(done.stdout)
        sys.stderr.write(done.stderr)
        return done.returncode

    report = collect(Path(args.db), args.require_recent_success)

    if args.brief:
        print(f"  {report['message_zh']}")
        t = report["relation_totals"]
        print(f"    收藏 {t['total_relations']} 条："
              f"{t['claimed_by_a_real_run']} 条有跑认领、"
              f"{t['no_run_id_at_all']} 条压根没记跑、"
              f"{t['run_id_points_at_a_missing_run']} 条指向已消失的跑")
        for row in report["latest_successful_automatic_run_by_platform"]:
            print(f"    {row['platform']}: 最近成功 {row['latest_success_at']}"
                  f"（{row['successful_runs']} 次，进 {row['imported'] or 0} 条）")
        for row in report["recent_failures"][:4]:
            print(f"    ✗ {row['platform']} {row['status']} "
                  f"{row['last_error_code'] or '(无错码)'} ×{row['runs']}"
                  f" 最近 {row['latest_at']}")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 6


if __name__ == "__main__":
    sys.exit(main())
