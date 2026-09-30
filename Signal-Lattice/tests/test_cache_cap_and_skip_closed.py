"""研究层收尾：原文缓存 LRU 上限；休市日由程序自己判断并快速退出（timer 做不了日历判断）。"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from signal_lattice import cache_cap, nyse_calendar, research_cycle as RC  # noqa: E402
from signal_lattice.evidence.text_similarity import TextCache  # noqa: E402


def _write(path: Path, size: int, used_at: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    os.utime(path, (used_at, used_at))


class PruneLruTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sl-cachecap-"))

    def test_under_the_cap_nothing_is_removed(self):
        _write(self.tmp / "sec" / "a.body", 100, 1000)
        stats = cache_cap.prune_lru([self.tmp / "sec"], 1000)
        self.assertEqual((stats["before"], stats["after"], stats["removed_files"]), (100, 100, 0))

    def test_least_recently_used_groups_go_first_and_pairs_go_together(self):
        sec = self.tmp / "sec"
        _write(sec / "aa" / "old.body.gz", 400, 1000)
        _write(sec / "aa" / "old.meta.json", 10, 1000)
        _write(sec / "bb" / "mid.body.gz", 400, 2000)
        _write(sec / "bb" / "mid.meta.json", 10, 2000)
        _write(sec / "cc" / "new.body.gz", 400, 3000)
        _write(sec / "cc" / "new.meta.json", 10, 3000)
        stats = cache_cap.prune_lru([sec], 900)
        left = sorted(p.name for p in sec.rglob("*") if p.is_file())
        self.assertEqual(left, ["mid.body.gz", "mid.meta.json", "new.body.gz", "new.meta.json"])
        self.assertEqual(stats["removed_files"], 2)
        self.assertLessEqual(stats["after"], 900)

    def test_a_cache_hit_refreshes_recency_so_it_survives(self):
        cache = TextCache(self.tmp / "text")
        cache.put("0001-26-000001", "a" * 3000)
        cache.put("0001-26-000002", "b" * 3000)
        for accession in ("0001-26-000001", "0001-26-000002"):
            os.utime(cache.path(accession), (1000, 1000))
        self.assertIsNotNone(cache.get("0001-26-000001"))            # 命中 -> 最近使用
        size = cache.path("0001-26-000001").stat().st_size
        cache_cap.prune_lru([self.tmp / "text"], size)
        self.assertTrue(cache.path("0001-26-000001").exists())
        self.assertFalse(cache.path("0001-26-000002").exists())

    def test_both_directories_count_against_one_cap(self):
        _write(self.tmp / "sec" / "a.body", 600, 1000)
        _write(self.tmp / "text" / "b.txt.gz", 600, 2000)
        stats = cache_cap.prune_lru([self.tmp / "sec", self.tmp / "text"], 1000)
        self.assertEqual(stats["after"], 600)
        self.assertTrue((self.tmp / "text" / "b.txt.gz").exists())

    def test_missing_directory_is_ignored(self):
        self.assertEqual(cache_cap.prune_lru([self.tmp / "nope"], 10)["removed_files"], 0)


class SkipWhenMarketClosedTests(unittest.TestCase):
    def _args(self, *extra):
        parser = argparse.ArgumentParser()
        RC.add_arguments(parser)
        tmp = Path(tempfile.mkdtemp(prefix="sl-skip-"))
        return parser.parse_args(["--work-dir", str(tmp / "w"), "--out-dir", str(tmp / "o"), "--offline", *extra])

    def _run(self, args, now):
        class FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return now.astimezone(tz) if tz else now

        out = io.StringIO()
        with mock.patch.object(RC, "datetime", FrozenDatetime), mock.patch.object(RC, "run_cycle", side_effect=AssertionError("closed day must not run")) as run:
            with contextlib.redirect_stdout(out):
                code = RC.cli_main(args, ROOT)
        return code, out.getvalue(), run

    def test_thanksgiving_exits_zero_without_running_anything(self):
        day = datetime(2026, 11, 26, 12, 0, tzinfo=nyse_calendar.NEW_YORK)
        self.assertFalse(nyse_calendar.is_trading_day(day.date()))
        code, text, run = self._run(self._args("--skip-if-market-closed"), day)
        self.assertEqual(code, 0)
        self.assertIn("休市", text)
        run.assert_not_called()

    def test_a_saturday_is_skipped_too(self):
        code, text, _ = self._run(self._args("--skip-if-market-closed"), datetime(2026, 10, 3, 17, 0, tzinfo=nyse_calendar.NEW_YORK))
        self.assertEqual(code, 0)
        self.assertIn("周末", text)

    def test_without_the_flag_a_closed_day_still_runs(self):
        args = self._args()
        with mock.patch.object(RC, "run_cycle", side_effect=RC.UniverseIncompleteError(1, 600, "test")) as run:
            with contextlib.redirect_stderr(io.StringIO()):
                code = RC.cli_main(args, ROOT)
        self.assertEqual(code, 3)
        run.assert_called_once()

    def test_the_cap_runs_after_the_cycle_even_when_it_fails(self):
        args = self._args("--cache-max-bytes", "123")
        with mock.patch.object(RC, "run_cycle", side_effect=RC.UniverseIncompleteError(1, 600, "test")), \
             mock.patch.object(RC.cache_cap, "prune_lru", return_value={"before": 1, "after": 1, "removed_files": 0}) as prune:
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                RC.cli_main(args, ROOT)
        self.assertEqual(prune.call_args.args[1], 123)


if __name__ == "__main__":
    unittest.main()
