"""facts.sqlite 与 universe-cache 的总量上限：只清读取窗口之外的旧期、保护窗口内数据、磁盘不够不做半截操作、清掉的不会被重新装回。"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import time
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from signal_lattice import db_cap  # noqa: E402
from signal_lattice.evidence.factstore import FactStore  # noqa: E402


def payload(ends):
    return {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
        {"val": 100.0 + i, "start": None, "end": end, "form": "10-K", "accn": "0000000000-25-%06d" % i, "filed": "2026-02-20"}
        for i, end in enumerate(ends)]}}}}}


class KeepFromTests(unittest.TestCase):
    def test_window_never_reaches_into_what_the_backtest_and_lookbacks_read(self):
        # 最早的 as_of 是 event_start 附近，往前最多读 4 年财务期；keep_from 必须比它再早 >= 2 年
        cutoff = date.fromisoformat(db_cap.keep_from("2026-10-01", "2024-10-01"))
        self.assertLessEqual(cutoff, date(2020, 10, 1) - timedelta(days=700))

    def test_retention_years_widens_the_window_when_as_of_is_far_ahead(self):
        self.assertEqual(db_cap.keep_from("2040-01-01", "2024-10-01"), "2018-10-01")
        self.assertEqual(db_cap.keep_from("2026-10-01", "2024-10-01", retention_years=12), "2014-10-01")


class PruneFactsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.path = self.tmp / "facts.sqlite"
        store = FactStore(self.path)
        ends = ["2012-12-31", "2015-12-31", "2018-09-30", "2018-12-31", "2022-12-31", "2025-12-31"]
        for cik in range(1, 201):
            store.ingest_companyfacts(cik, payload(ends), date(2026, 9, 1))
        store.ingest_submissions(1, {"name": "X", "tickers": ["X"], "exchanges": ["N"], "sic": "1",
                                     "filings": {"recent": {"accessionNumber": ["0000000000-26-000001"], "form": ["10-K"],
                                                            "filingDate": ["2026-02-20"], "reportDate": ["2025-12-31"],
                                                            "primaryDocument": ["a.htm"], "items": [""]}}}, date(2026, 9, 1))
        store.close()

    def ends(self):
        with sqlite3.connect(self.path) as db:
            return [r[0] for r in db.execute("SELECT DISTINCT period_end FROM facts ORDER BY 1")]

    def test_under_the_cap_nothing_is_deleted(self):
        out = db_cap.prune_facts(self.path, 1 << 40, "2018-10-01")
        self.assertEqual(out["deleted_rows"], 0)
        self.assertEqual(len(self.ends()), 6)

    def test_over_the_cap_only_rows_older_than_keep_from_go_and_the_file_shrinks(self):
        before = db_cap.file_bytes(self.path)
        out = db_cap.prune_facts(self.path, 1, "2018-10-01")                       # 上限设到 1 字节 = 必然超
        self.assertEqual(self.ends(), ["2018-12-31", "2022-12-31", "2025-12-31"])  # 窗口内的一行不少
        self.assertEqual(out["deleted_rows"], 200 * 3)
        self.assertTrue(out["vacuumed"])
        self.assertLess(out["after"], before)
        self.assertTrue(out["still_over_cap"])                                     # 已无可删：只告警，不继续啃窗口内的数据
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM filings").fetchone()[0], 1)    # 申报清单不动
            self.assertEqual(db.execute("SELECT COUNT(*) FROM entities").fetchone()[0], 1)                      # 实体表不动

    def test_running_again_is_a_no_op(self):
        db_cap.prune_facts(self.path, 1, "2018-10-01")
        again = db_cap.prune_facts(self.path, 1, "2018-10-01")
        self.assertEqual(again["deleted_rows"], 0)

    def test_not_enough_free_disk_skips_everything(self):
        out = db_cap.prune_facts(self.path, 1, "2018-10-01", free_bytes=10)
        self.assertIn("磁盘", out["skipped"])
        self.assertEqual(len(self.ends()), 6)

    def test_disabled_and_missing_are_skipped(self):
        self.assertEqual(db_cap.prune_facts(self.path, 0, "2018-10-01")["skipped"], "disabled")
        self.assertEqual(db_cap.prune_facts(self.tmp / "nope.sqlite", 10, "2018-10-01")["skipped"], "missing")
        self.assertEqual(len(self.ends()), 6)

    def test_a_write_locked_database_is_left_alone_not_corrupted(self):
        blocker = sqlite3.connect(self.path)
        blocker.execute("BEGIN EXCLUSIVE")
        try:
            out = db_cap.prune_facts(self.path, 1, "2018-10-01", lock_timeout=0.2)
        finally:
            blocker.rollback()
            blocker.close()
        self.assertIn("sqlite", out["skipped"])
        self.assertEqual(len(self.ends()), 6)

    def test_pruned_old_periods_are_not_reingested_when_the_store_has_a_floor(self):
        db_cap.prune_facts(self.path, 1, "2018-10-01")
        store = FactStore(self.path)
        store.min_period_end = "2018-10-01"
        added = store.ingest_companyfacts(1, payload(["2012-12-31", "2019-06-30"]), date(2026, 9, 2))
        store.close()
        self.assertEqual(added, 1)                                                   # 只装回窗口内的新期
        self.assertNotIn("2012-12-31", self.ends())

    def test_without_a_floor_the_store_behaves_exactly_as_before(self):
        store = FactStore(self.path)
        added = store.ingest_companyfacts(999, payload(["2012-12-31"]), date(2026, 9, 2))
        store.close()
        self.assertEqual(added, 1)


class UniverseCacheTests(unittest.TestCase):
    def test_least_recently_used_files_go_first_and_recent_hits_survive(self):
        root = Path(tempfile.mkdtemp())
        now = time.time()
        for index, name in enumerate(["a.json", "b.json", "c.json"]):
            (root / name).write_bytes(b"x" * 100)
            os.utime(root / name, (now - 1000 + index, now - 1000 + index))
        from signal_lattice import cache_cap
        cache_cap.touch(root / "a.json")                                              # a 被本轮命中，最后才淘汰
        out = db_cap.prune_universe_cache(root, 200)
        self.assertEqual(out["removed_files"], 1)
        self.assertEqual(sorted(p.name for p in root.iterdir()), ["a.json", "c.json"])

    def test_disk_cache_hit_refreshes_recency(self):
        from signal_lattice.marketdata import DiskCache
        root = Path(tempfile.mkdtemp())
        cache = DiskCache(root)
        cache.save("k", b"[]")
        old = time.time() - 5000
        os.utime(root / "k.json", (old, old))
        self.assertEqual(cache.load("k", 10 ** 9), b"[]")
        self.assertGreater((root / "k.json").stat().st_mtime, old + 1000)

    def test_zero_disables(self):
        root = Path(tempfile.mkdtemp())
        (root / "a.json").write_bytes(b"x" * 100)
        self.assertEqual(db_cap.prune_universe_cache(root, 0)["removed_files"], 0)
        self.assertTrue((root / "a.json").is_file())


if __name__ == "__main__":
    unittest.main()
