#!/usr/bin/env python3
"""一次性迁移：把 Cloudflare D1 `adp-mirror` 的导出内容导入自托管的本地 SQLite。

只用标准库，不联网，不需要任何 Cloudflare 凭据——导出由有权限的人在另一边做好，本脚本只读导出文件。

输入二选一：
  --sql  dump.sql          `wrangler d1 export adp-mirror --remote --output dump.sql` 的输出
  --json-dir DIR           每张表一个 <表名>.json；内容可以是 [{行},...] 或 wrangler `d1 execute --json` 的
                           [{"results":[{行},...], ...}]
  --json FILE              单个 JSON：{"cn_items":[{行},...], "cn_reviews":[...], ...}

用法：
  python3 migrate_from_d1.py --db /var/lib/adp/adp.sqlite --sql dump.sql
  python3 migrate_from_d1.py --db /var/lib/adp/adp.sqlite --sql dump.sql --dry-run     # 只校验，不写

做什么：
  1. 目标库按 deploy/cloudflare/schema_cloud.sql 建表（与网页服务启动时用的是同一份），再补 worker 运行时才建的 4 张表；
  2. 目标库里已有业务数据时拒绝（防止覆盖线上已在跑的库），除非 --force（此时 INSERT OR REPLACE）；
  3. 已有库文件先整份复制一份 *.pre-import-<时间戳> 再动；
  4. 整个导入在一个事务里，出错整体回滚；
  5. 导入后逐表核对行数与内容摘要（源 vs 目标，sha256），任何不一致退出码 1；再跑 PRAGMA integrity_check；
  6. 输出一份 JSON 报告（逐表行数、被跳过的表/列）。

退出码：0 成功；1 核对不一致/导入出错；2 参数或输入文件问题；3 目标库非空且未给 --force。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_SCHEMA = HERE.parent / "cloudflare" / "schema_cloud.sql"

# 要搬的业务表（顺序无依赖，schema 里没有外键）。
CORE_TABLES = [
    "cn_sources", "cn_items", "cn_selections", "cn_lessons", "cn_reviews",
    "cn_events", "cn_run_log", "cn_meta", "cn_artifacts",
]
# worker 运行时用 CREATE TABLE IF NOT EXISTS 才建的表；D1 里多半已有，自托管库这里预建，保证导入后结构一致。
# 必须与 worker_cloud.js 里的语句一致——tests/test_selfhost_migration.py 有一条测试逐字比对。
RUNTIME_DDL = {
    "cn_item_meta": "CREATE TABLE IF NOT EXISTS cn_item_meta (item_id TEXT PRIMARY KEY, doi TEXT, oa_id TEXT, work_type TEXT, is_preprint INTEGER, venue TEXT, venue_type TEXT, cited_by INTEGER, oa_status TEXT, pub_year INTEGER, authors_n INTEGER, found INTEGER NOT NULL DEFAULT 0, enriched_at TEXT NOT NULL)",
    "cn_watchlist": "CREATE TABLE IF NOT EXISTS cn_watchlist (id TEXT PRIMARY KEY, facet TEXT NOT NULL, value TEXT NOT NULL, created_at TEXT NOT NULL)",
    "cn_watch_seen": "CREATE TABLE IF NOT EXISTS cn_watch_seen (watch_id TEXT NOT NULL, item_id TEXT NOT NULL, at TEXT NOT NULL, PRIMARY KEY (watch_id, item_id))",
    "cn_rum": "CREATE TABLE IF NOT EXISTS cn_rum (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, metric TEXT, value REAL, theme TEXT, route TEXT, device TEXT, network TEXT, build_id TEXT)",
}
ALL_TABLES = CORE_TABLES + list(RUNTIME_DDL)
# 有业务意义的表：目标库里这些表有数据 = 不是一个空库。
GUARD_TABLES = ["cn_items", "cn_selections", "cn_lessons", "cn_reviews", "cn_events", "cn_run_log"]
# 明确知道、可以放心忽略的来源表（旧镜像架构 / D1 与 SQLite 的内部表）。其它没见过的表会在报告里列出来但不阻断。
KNOWN_IGNORED = {
    "mirror_meta", "lessons_mirror", "selections_mirror", "manifests_mirror", "review_mirror", "events_inbox",
    "_cf_KV", "d1_migrations", "sqlite_sequence", "sqlite_stat1", "sqlite_stat4",
}


class MigrationError(Exception):
    def __init__(self, msg: str, code: int = 1):
        super().__init__(msg)
        self.code = code


def qi(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def table_cols(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({qi(table)})")]


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def digest(rows: list[tuple]) -> str:
    """行集合的顺序无关摘要：每行按 repr 归一后排序再 sha256。"""
    h = hashlib.sha256()
    for line in sorted(json.dumps(list(r), ensure_ascii=False, default=repr) for r in rows):
        h.update(line.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


# ---------------------------------------------------------------- 读来源

class Source:
    """统一接口：tables() 列出来源里有的表；columns(t)；rows(t) -> list[tuple]（与 columns 同序）。"""

    def tables(self) -> list[str]: raise NotImplementedError
    def columns(self, t: str) -> list[str]: raise NotImplementedError
    def rows(self, t: str) -> list[tuple]: raise NotImplementedError
    def close(self) -> None: pass


class SqlDumpSource(Source):
    def __init__(self, path: Path):
        self._tmp = tempfile.TemporaryDirectory(prefix="adp-d1-dump-")
        self._conn = sqlite3.connect(str(Path(self._tmp.name) / "scratch.sqlite"))
        text = path.read_text(encoding="utf-8")
        try:
            self._conn.executescript(text)
        except sqlite3.Error as e:
            raise MigrationError(f"导出文件 {path} 不是可执行的 SQLite 脚本：{e}", 2) from e

    def tables(self):
        return [r[0] for r in self._conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]

    def columns(self, t): return table_cols(self._conn, t)
    def rows(self, t): return [tuple(r) for r in self._conn.execute(f"SELECT * FROM {qi(t)}")]

    def close(self):
        self._conn.close()
        self._tmp.cleanup()


class JsonSource(Source):
    def __init__(self, data: dict[str, list[dict]]):
        self._data = data

    def tables(self): return sorted(self._data)

    def columns(self, t):
        cols: list[str] = []
        for row in self._data[t]:
            for k in row:
                if k not in cols:
                    cols.append(k)
        return cols

    def rows(self, t):
        cols = self.columns(t)
        return [tuple(row.get(c) for c in cols) for row in self._data[t]]


def _unwrap(obj, where: str) -> list[dict]:
    """接受 [{行}] 或 wrangler 的 [{"results":[{行}], "success":true}]。"""
    if isinstance(obj, dict) and "results" in obj:
        obj = obj["results"]
    if isinstance(obj, list) and obj and isinstance(obj[0], dict) and "results" in obj[0] and "success" in obj[0]:
        merged: list[dict] = []
        for part in obj:
            merged.extend(part.get("results") or [])
        return merged
    if isinstance(obj, list) and all(isinstance(r, dict) for r in obj):
        return obj
    raise MigrationError(f"{where} 的 JSON 形状不认识（要 [{{行}}] 或 wrangler 的 [{{\"results\":[...]}}]）", 2)


def load_json_dir(d: Path) -> JsonSource:
    if not d.is_dir():
        raise MigrationError(f"--json-dir {d} 不是目录", 2)
    data = {}
    for f in sorted(d.glob("*.json")):
        try:
            data[f.stem] = _unwrap(json.loads(f.read_text(encoding="utf-8")), f.name)
        except json.JSONDecodeError as e:
            raise MigrationError(f"{f} 不是合法 JSON：{e}", 2) from e
    if not data:
        raise MigrationError(f"{d} 里没有 *.json", 2)
    return JsonSource(data)


def load_json_file(f: Path) -> JsonSource:
    try:
        obj = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise MigrationError(f"读 {f} 失败：{e}", 2) from e
    if not isinstance(obj, dict):
        raise MigrationError(f"{f} 顶层必须是 {{表名: [行]}}", 2)
    return JsonSource({t: _unwrap(rows, f"{f.name}:{t}") for t, rows in obj.items()})


# ---------------------------------------------------------------- 导入

def prepare_target(conn: sqlite3.Connection, schema: Path) -> None:
    conn.executescript(schema.read_text(encoding="utf-8"))
    for ddl in RUNTIME_DDL.values():
        conn.execute(ddl)
    conn.commit()


def target_has_data(conn: sqlite3.Connection) -> dict[str, int]:
    out = {}
    for t in GUARD_TABLES:
        n = conn.execute(f"SELECT COUNT(*) FROM {qi(t)}").fetchone()[0]
        if n:
            out[t] = n
    return out


def migrate(db_path: Path, source: Source, schema: Path = DEFAULT_SCHEMA, force: bool = False, dry_run: bool = False) -> dict:
    report: dict = {"db": str(db_path), "dry_run": dry_run, "tables": {}, "skipped_tables": [], "dropped_columns": {}, "backup": None}
    src_tables = source.tables()
    report["skipped_tables"] = sorted(t for t in src_tables if t not in ALL_TABLES)
    report["unknown_tables"] = [t for t in report["skipped_tables"] if t not in KNOWN_IGNORED]
    if not any(t in src_tables for t in ("cn_items", "cn_run_log")):
        raise MigrationError("来源里既没有 cn_items 也没有 cn_run_log——这不像 adp-mirror 的导出，已拒绝（没有动目标库）", 2)

    real = db_path.exists() and db_path.stat().st_size > 0
    work_path = db_path
    tmp = None
    if dry_run:
        tmp = tempfile.TemporaryDirectory(prefix="adp-migrate-dry-")
        work_path = Path(tmp.name) / "dry.sqlite"
        if real:
            shutil.copy2(db_path, work_path)
    elif real:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        bak = db_path.with_name(db_path.name + f".pre-import-{stamp}")
        src_conn = sqlite3.connect(str(db_path))
        try:
            dst_conn = sqlite3.connect(str(bak))
            with dst_conn:
                src_conn.backup(dst_conn)   # 在线一致性备份，比 cp 对 WAL 库更稳
            dst_conn.close()
        finally:
            src_conn.close()
        report["backup"] = str(bak)
    work_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(work_path), isolation_level=None)   # 手动管事务
    try:
        prepare_target(conn, schema)
        existing = target_has_data(conn)
        if existing and not force:
            raise MigrationError(f"目标库不是空的（{existing}）。确认要覆盖同主键行请加 --force；默认拒绝以免冲掉线上数据。", 3)
        verb = "INSERT OR REPLACE" if force else "INSERT"
        conn.execute("BEGIN")
        try:
            for t in ALL_TABLES:
                if t not in src_tables:
                    report["tables"][t] = {"source_rows": 0, "note": "来源里没有这张表"}
                    continue
                scols, tcols = source.columns(t), table_cols(conn, t)
                common = [c for c in scols if c in tcols]
                dropped = [c for c in scols if c not in tcols]
                if dropped:
                    report["dropped_columns"][t] = dropped
                rows = source.rows(t)
                idx = [scols.index(c) for c in common]
                proj = [tuple(r[i] for i in idx) for r in rows]
                if proj:
                    sql = f"{verb} INTO {qi(t)} ({', '.join(qi(c) for c in common)}) VALUES ({', '.join('?' for _ in common)})"
                    try:
                        conn.executemany(sql, proj)
                    except sqlite3.Error as e:
                        raise MigrationError(f"导入 {t} 失败：{e}", 1) from e
                report["tables"][t] = {"source_rows": len(proj), "_proj": proj, "_cols": common}
            # ---- 核对：行数 + 内容摘要
            mismatches = []
            for t, info in report["tables"].items():
                proj = info.pop("_proj", None)
                cols = info.pop("_cols", None)
                if proj is None:
                    continue
                order = ", ".join(qi(c) for c in cols)
                got = [tuple(r) for r in conn.execute(f"SELECT {order} FROM {qi(t)}")]
                info["target_rows"] = len(got)
                if not force:
                    want = digest(proj)
                    info["sha256"] = want
                    if len(got) != len(proj) or digest(got) != want:
                        mismatches.append(t)
                else:
                    # --force 时目标里可能本就有别的行：只要求来源每一行都在目标里
                    gotset = {json.dumps(list(r), default=repr) for r in got}
                    missing = [1 for r in proj if json.dumps(list(r), default=repr) not in gotset]
                    if missing:
                        mismatches.append(t)
            if mismatches:
                raise MigrationError(f"导入后核对不一致：{mismatches}（已整体回滚）", 1)
            if dry_run:
                conn.execute("ROLLBACK")
            else:
                conn.execute("COMMIT")
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        ic = conn.execute("PRAGMA integrity_check").fetchone()[0]
        report["integrity_check"] = ic
        if ic != "ok":
            raise MigrationError(f"PRAGMA integrity_check 不是 ok：{ic}", 1)
    finally:
        conn.close()
        if tmp:
            tmp.cleanup()
    report["ok"] = True
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="把 D1 adp-mirror 的导出导入自托管 SQLite（一次性）")
    ap.add_argument("--db", required=True, type=Path, help="目标 SQLite 文件（自托管 /var/lib/adp/adp.sqlite）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--sql", type=Path)
    g.add_argument("--json-dir", type=Path)
    g.add_argument("--json", type=Path)
    ap.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    ap.add_argument("--force", action="store_true", help="目标库已有数据时也导入（同主键行被来源覆盖）")
    ap.add_argument("--dry-run", action="store_true", help="在临时副本上演练，不写目标库")
    a = ap.parse_args(argv)
    try:
        if a.sql:
            if not a.sql.is_file():
                raise MigrationError(f"{a.sql} 不存在", 2)
            src: Source = SqlDumpSource(a.sql)
        elif a.json_dir:
            src = load_json_dir(a.json_dir)
        else:
            src = load_json_file(a.json)
        try:
            rep = migrate(a.db, src, a.schema, a.force, a.dry_run)
        finally:
            src.close()
    except MigrationError as e:
        print(json.dumps({"ok": False, "error": str(e), "exit_code": e.code}, ensure_ascii=False), file=sys.stderr)
        return e.code
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
