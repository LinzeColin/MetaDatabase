"""D1 -> 自托管 SQLite 一次性迁移脚本的测试。

夹具全部自造：先按 schema_cloud.sql 造一个「假 D1」库，灌入各表数据，再用 sqlite 的 iterdump() 导出成与
`wrangler d1 export` 同类的 SQL 脚本（BEGIN/CREATE/INSERT/COMMIT，含旧镜像表、_cf_KV、sqlite_sequence 这些噪声），
也导出成 JSON。然后真跑迁移脚本，核对行数、内容摘要、拒绝覆盖、回滚与「迁移后的库网页服务能直接读」。
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SELFHOST = ROOT / "deploy" / "selfhost"
sys.path.insert(0, str(SELFHOST))
import migrate_from_d1 as mig  # noqa: E402

SCHEMA = ROOT / "deploy" / "cloudflare" / "schema_cloud.sql"
WORKER = ROOT / "deploy" / "cloudflare" / "worker_cloud.js"
NODE = shutil.which("node")


def build_fake_d1(path: Path) -> dict[str, int]:
    """造一个带代表性数据的「线上 D1」。返回各表行数。"""
    c = sqlite3.connect(path)
    c.executescript(SCHEMA.read_text(encoding="utf-8"))
    for ddl in mig.RUNTIME_DDL.values():
        c.execute(ddl)
    c.executescript(
        """
        CREATE TABLE mirror_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);       -- 旧镜像架构遗留
        CREATE TABLE events_inbox (id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT);
        CREATE TABLE _cf_KV (key TEXT PRIMARY KEY, value BLOB) WITHOUT ROWID;       -- D1 内部表
        INSERT INTO mirror_meta VALUES ('x','y');
        INSERT INTO events_inbox (payload) VALUES ('legacy');
        """
    )
    c.execute("INSERT INTO cn_sources (id,board_id,name,platform,website,method,feed_url,official,cadence,health,consecutive_failures,last_fetch) VALUES ('arxiv-all','board1','arXiv 全站','OAI','https://arxiv.org','arxiv',NULL,1,'每日','active',0,'2026-09-29T20:31:00Z')")
    c.execute("INSERT INTO cn_sources (id,board_id,name,method,feed_url,official,health,consecutive_failures) VALUES ('nature','board2','Nature','rss','https://x.test/n.rss',1,'degraded',2)")
    items = []
    for i in range(1, 41):
        title = f"迁移夹具论文 {i}：带引号 ' \" 和换行\n第二行 与 emoji 📚"
        items.append((f"arxiv:2609.{10000+i}", "board1", "arxiv-all", "paper", title, f"https://arxiv.org/abs/2609.{10000+i}", f"摘要 {i}", "cs.AI,cs.LG", "A, B", f"2026-09-2{i%9}T00:00:00.000Z", "2026-09-29T20:31:00Z", "2026-09-29T20:31:00Z"))
    c.executemany("INSERT INTO cn_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", items)
    c.execute("INSERT INTO cn_selections VALUES ('2026-09-29','arxiv:2609.10001',71.5,'因为相关',0,NULL,'{\"relevance\":1}','board1','2026-09-29T20:31:05Z')")
    c.execute("INSERT INTO cn_lessons VALUES ('L1','2026-09-29','arxiv:2609.10001','讲义标题','https://arxiv.org/abs/2609.10001','[{\"title\":\"人话版\",\"sentences\":[{\"text\":\"迁移夹具讲义\"}]}]','template','v3','2026-09-29T20:31:06Z')")
    c.execute("INSERT INTO cn_reviews VALUES ('arxiv:2609.10001','2026-10-03T00:00:00Z',3.1,5.2,2,0,2,'2026-09-29T21:00:00Z',3,'学习中')")
    c.execute("INSERT INTO cn_events (item_id,kind,grade,at,dedup_key) VALUES ('arxiv:2609.10001','grade',3,'2026-09-29T21:00:00Z','arxiv:2609.10001:2026-09-30')")
    c.execute("INSERT INTO cn_events (item_id,kind,grade,at,dedup_key) VALUES ('arxiv:2609.10001','reveal',NULL,'2026-09-29T20:59:00Z',NULL)")
    c.execute("INSERT INTO cn_run_log VALUES ('2026-09-29T2030-cron','2026-09-29','正常','{\"arxiv\":220,\"biorxiv\":60,\"feeds\":40,\"candidates\":300,\"degraded\":[]}',NULL,'2026-09-29T20:32:00Z')")
    c.execute("INSERT INTO cn_meta VALUES ('backfill_from','2019-03-01')")
    c.execute("INSERT INTO cn_artifacts VALUES ('raw/x/v1/ab/cd/abcd.xml','abcd','nature','https://x.test','application/xml',12,'none','v1','2026-09-29T20:31:00Z')")
    c.execute("INSERT INTO cn_item_meta VALUES ('arxiv:2609.10001','10.48550/arxiv.2609.10001','W1','article',1,'arXiv','repository',3,'green',2026,2,1,'2026-09-29T20:40:00Z')")
    c.execute("INSERT INTO cn_watchlist VALUES ('w:1','keyword','attention','2026-09-28T00:00:00Z')")
    c.execute("INSERT INTO cn_watch_seen VALUES ('w:1','arxiv:2609.10002','2026-09-29T00:00:00Z')")
    c.execute("INSERT INTO cn_rum (ts,metric,value,theme,route,device,network,build_id) VALUES ('2026-09-29T00:00:00Z','LCP',1.2,'warm','today','mobile','4g','abc')")
    c.commit()
    counts = {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in mig.ALL_TABLES}
    c.close()
    return counts


def dump_sql(db: Path, out: Path) -> None:
    c = sqlite3.connect(db)
    out.write_text("PRAGMA defer_foreign_keys=TRUE;\n" + "\n".join(c.iterdump()) + "\n", encoding="utf-8")
    c.close()


def dump_json(db: Path, out: Path, *, wrangler_shape: bool) -> None:
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    out.mkdir()
    for t in mig.ALL_TABLES:
        rows = [dict(r) for r in c.execute(f"SELECT * FROM {t}")]
        payload = [{"results": rows, "success": True, "meta": {"rows_read": len(rows)}}] if wrangler_shape else rows
        (out / f"{t}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    c.close()


def table_counts(db: Path) -> dict[str, int]:
    c = sqlite3.connect(db)
    try:
        return {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in mig.ALL_TABLES}
    finally:
        c.close()


class MigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.fake = self.tmp / "fake_d1.sqlite"
        self.counts = build_fake_d1(self.fake)
        self.sql = self.tmp / "dump.sql"
        dump_sql(self.fake, self.sql)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SELFHOST / "migrate_from_d1.py"), *args], capture_output=True, text=True)

    # ---- SQL 导出
    def test_sql_dump_imports_every_table_with_matching_counts_and_digests(self) -> None:
        target = self.tmp / "adp.sqlite"
        p = self.run_cli("--db", str(target), "--sql", str(self.sql))
        self.assertEqual(p.returncode, 0, p.stderr)
        rep = json.loads(p.stdout)
        self.assertTrue(rep["ok"]); self.assertEqual(rep["integrity_check"], "ok")
        self.assertEqual(table_counts(target), self.counts)
        for t, n in self.counts.items():
            self.assertEqual(rep["tables"][t]["source_rows"], n, t)
            self.assertEqual(rep["tables"][t]["target_rows"], n, t)
            if n:
                self.assertRegex(rep["tables"][t]["sha256"], r"^[0-9a-f]{64}$")
        self.assertIn("mirror_meta", rep["skipped_tables"]); self.assertIn("events_inbox", rep["skipped_tables"]); self.assertIn("_cf_KV", rep["skipped_tables"])
        self.assertEqual(rep["unknown_tables"], [], "旧镜像表/内部表都是已知可忽略的")

    def test_content_survives_byte_for_byte_including_quotes_newlines_emoji_and_autoincrement_ids(self) -> None:
        target = self.tmp / "adp.sqlite"
        self.assertEqual(self.run_cli("--db", str(target), "--sql", str(self.sql)).returncode, 0)
        a, b = sqlite3.connect(self.fake), sqlite3.connect(target)
        for t in ("cn_items", "cn_events", "cn_reviews", "cn_run_log", "cn_rum", "cn_watchlist"):
            cols = ", ".join(mig.table_cols(a, t))
            self.assertEqual(a.execute(f"SELECT {cols} FROM {t} ORDER BY 1").fetchall(), b.execute(f"SELECT {cols} FROM {t} ORDER BY 1").fetchall(), t)
        self.assertIn("\n第二行 与 emoji 📚", b.execute("SELECT title FROM cn_items WHERE id='arxiv:2609.10001'").fetchone()[0])
        # 自增主键接着往下走，不会撞已导入的 id
        b.execute("INSERT INTO cn_events (item_id,kind,grade,at,dedup_key) VALUES ('z','grade',1,'t','k-new')")
        self.assertGreater(b.execute("SELECT MAX(id) FROM cn_events").fetchone()[0], 2)
        a.close(); b.close()

    # ---- JSON 导出
    def test_json_dir_plain_rows_and_wrangler_shape_both_work(self) -> None:
        for shape in (False, True):
            d = self.tmp / f"json_{shape}"
            dump_json(self.fake, d, wrangler_shape=shape)
            target = self.tmp / f"adp_{shape}.sqlite"
            p = self.run_cli("--db", str(target), "--json-dir", str(d))
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(table_counts(target), self.counts, f"wrangler_shape={shape}")

    def test_single_json_file(self) -> None:
        d = self.tmp / "j"; dump_json(self.fake, d, wrangler_shape=False)
        one = self.tmp / "all.json"
        one.write_text(json.dumps({p.stem: json.loads(p.read_text(encoding="utf-8")) for p in d.glob("*.json")}, ensure_ascii=False), encoding="utf-8")
        target = self.tmp / "adp.sqlite"
        self.assertEqual(self.run_cli("--db", str(target), "--json", str(one)).returncode, 0)
        self.assertEqual(table_counts(target), self.counts)

    # ---- 安全性
    def test_refuses_nonempty_target_without_force_and_leaves_it_untouched(self) -> None:
        target = self.tmp / "adp.sqlite"
        self.assertEqual(self.run_cli("--db", str(target), "--sql", str(self.sql)).returncode, 0)
        c = sqlite3.connect(target); c.execute("UPDATE cn_items SET title='线上已改过'"); c.commit(); c.close()
        p = self.run_cli("--db", str(target), "--sql", str(self.sql))
        self.assertEqual(p.returncode, 3, p.stderr)
        self.assertIn("--force", p.stderr)
        c = sqlite3.connect(target)
        self.assertEqual(c.execute("SELECT DISTINCT title FROM cn_items").fetchall(), [("线上已改过",)])
        c.close()

    def test_force_overwrites_same_keys_and_keeps_a_pre_import_backup(self) -> None:
        target = self.tmp / "adp.sqlite"
        self.assertEqual(self.run_cli("--db", str(target), "--sql", str(self.sql)).returncode, 0)
        c = sqlite3.connect(target); c.execute("UPDATE cn_items SET title='线上已改过'"); c.commit(); c.close()
        p = self.run_cli("--db", str(target), "--sql", str(self.sql), "--force")
        self.assertEqual(p.returncode, 0, p.stderr)
        rep = json.loads(p.stdout)
        bak = Path(rep["backup"]); self.assertTrue(bak.exists())
        c = sqlite3.connect(bak); self.assertEqual(c.execute("SELECT DISTINCT title FROM cn_items").fetchall(), [("线上已改过",)]); c.close()
        c = sqlite3.connect(target); self.assertIn("迁移夹具论文 1", c.execute("SELECT title FROM cn_items WHERE id='arxiv:2609.10001'").fetchone()[0]); c.close()

    def test_dry_run_writes_nothing(self) -> None:
        target = self.tmp / "adp.sqlite"
        p = self.run_cli("--db", str(target), "--sql", str(self.sql), "--dry-run")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(json.loads(p.stdout)["dry_run"])
        self.assertFalse(target.exists(), "dry-run 不得创建目标库")

    def test_corrupt_or_foreign_input_is_rejected_before_touching_target(self) -> None:
        target = self.tmp / "adp.sqlite"
        bad = self.tmp / "bad.sql"; bad.write_text("THIS IS NOT SQL;", encoding="utf-8")
        p = self.run_cli("--db", str(target), "--sql", str(bad))
        self.assertEqual(p.returncode, 2); self.assertFalse(target.exists())
        other = self.tmp / "other.sql"; other.write_text("CREATE TABLE foo(a); INSERT INTO foo VALUES (1);", encoding="utf-8")
        p = self.run_cli("--db", str(target), "--sql", str(other))
        self.assertEqual(p.returncode, 2); self.assertIn("不像 adp-mirror", p.stderr)
        self.assertEqual(self.run_cli("--db", str(target), "--sql", str(self.tmp / "missing.sql")).returncode, 2)

    def test_failure_midway_rolls_back_everything(self) -> None:
        """导出里 cn_reviews 的一行违反 NOT NULL（reps 给了 NULL）-> 整体回滚，前面已导入的表也不留。"""
        broken = sqlite3.connect(self.fake); broken.execute("PRAGMA writable_schema=0")
        broken.executescript("CREATE TABLE cn_reviews_x AS SELECT * FROM cn_reviews; DROP TABLE cn_reviews;"
                             "CREATE TABLE cn_reviews (item_id TEXT, due_at TEXT, stability REAL, difficulty REAL, reps INTEGER, lapses INTEGER, state INTEGER, last_review TEXT, last_grade INTEGER, evidence_state TEXT);"
                             "INSERT INTO cn_reviews SELECT * FROM cn_reviews_x; UPDATE cn_reviews SET reps=NULL; DROP TABLE cn_reviews_x;")
        broken.commit(); broken.close()
        bad_sql = self.tmp / "bad_rows.sql"; dump_sql(self.fake, bad_sql)
        target = self.tmp / "adp.sqlite"
        p = self.run_cli("--db", str(target), "--sql", str(bad_sql))
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertEqual(table_counts(target)["cn_items"], 0, "回滚后不应留下半截数据")

    def test_runtime_ddl_matches_worker_source_verbatim(self) -> None:
        """迁移脚本里预建的 4 张运行时表 DDL 必须与 worker_cloud.js 里的 CREATE TABLE 语句一致，防止两边悄悄分叉。"""
        src = WORKER.read_text(encoding="utf-8")
        for name, ddl in mig.RUNTIME_DDL.items():
            self.assertIn(f"'{ddl}'", src, f"worker_cloud.js 里找不到与迁移脚本一致的 {name} 建表语句")

    # ---- 迁移后的库能直接被网页服务读
    @unittest.skipUnless(NODE, "需要 node")
    def test_migrated_database_is_served_by_the_selfhost_web_app(self) -> None:
        target = self.tmp / "adp.sqlite"
        self.assertEqual(self.run_cli("--db", str(target), "--sql", str(self.sql)).returncode, 0)
        p = subprocess.run([NODE, "--disable-warning=ExperimentalWarning", str(SELFHOST / "tests" / "smoke_render.mjs"), str(target)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        out = json.loads(p.stdout)
        for path, r in out["pages"].items():
            self.assertEqual(r["status"], 200, path)
            self.assertTrue(r["has_title"], path)
        self.assertIn("/item/arxiv%3A2609.10001", out["pages"])
        st = out["status"]
        self.assertEqual(st["db"]["items"], 40); self.assertEqual(st["db"]["events"], 2)
        self.assertEqual(st["latest_completed_run"]["arxiv"], 220)
        self.assertEqual(st["last_daily_job"], None)
        # 新鲜与否取决于夹具时间与「现在」的距离，不在这里断言；只要求判定字段被算出来了
        self.assertIsInstance(st["data_age_hours"], (int, float))
        self.assertIsInstance(st["fresh"], bool)


if __name__ == "__main__":
    unittest.main()
