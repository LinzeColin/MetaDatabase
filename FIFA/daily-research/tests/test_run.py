import copy
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fifa_daily import run as runmod
from tests.helpers import synth_raw

NOW = datetime(2026, 9, 30, 20, 40, tzinfo=timezone.utc)  # 悉尼 10-01 06:40（AEST 直到 10-04 才切夏令时）


def future_fixtures(raw, when: date):
    """给每个联赛加几场未来比赛，覆盖「有比赛」的路径。"""
    for comp in ("en.1", "es.1"):
        rows = raw["by_source"][f"openfootball:{comp}:2026-27"]
        a, b = rows[0]["home"], rows[0]["away"]
        rows.append({"comp": comp, "season": "2026-27", "date": when.isoformat(),
                     "kickoff_utc": f"{when.isoformat()}T14:00Z", "home": a, "away": b, "hg": None, "ag": None,
                     "round": "Matchday 9", "source": "test"})
    raw["matches"] = [m for rows in raw["by_source"].values() for m in rows]


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.site = Path(self.tmp.name) / "fifa"

    def tearDown(self):
        self.tmp.cleanup()

    def raw(self):
        r = synth_raw(NOW.date())
        future_fixtures(r, NOW.date() + timedelta(days=3))
        return r

    def status(self):
        return json.loads((self.site / "status.json").read_text(encoding="utf-8"))

    def test_success_writes_everything_and_says_fresh(self):
        code = runmod.run(self.site, NOW, raw=self.raw(), skip_backtest=True)
        self.assertEqual(code, 0)
        for f in ("index.html", "latest.json", "status.json", "archive/2026-10-01.json", "archive/2026-10-01.html",
                  "data/ledger.json", "data/runs.json", "data/matches-cache.json.gz"):
            self.assertTrue((self.site / f).exists(), f)
        page = (self.site / "index.html").read_text(encoding="utf-8")
        self.assertIn("今天的新报告已生成", page)
        self.assertIn("暂无合法盘口源", page)
        self.assertIn("只研究", page)
        rep = json.loads((self.site / "latest.json").read_text(encoding="utf-8"))
        self.assertEqual(rep["report_date"], "2026-10-01")
        self.assertEqual(len(rep["fixtures"]), 2)
        for fx in rep["fixtures"]:
            p = fx["p"]
            self.assertAlmostEqual(p["home"] + p["draw"] + p["away"], 1.0, places=6)
            self.assertFalse(fx["market"]["available"])
        ledger = json.loads((self.site / "data/ledger.json").read_text(encoding="utf-8"))
        self.assertEqual(len(ledger["entries"]), 2)
        self.assertTrue(self.status()["ok"])

    def test_rerun_same_day_is_idempotent(self):
        runmod.run(self.site, NOW, raw=self.raw(), skip_backtest=True)
        first = (self.site / "data/ledger.json").read_text(encoding="utf-8")
        runmod.run(self.site, NOW + timedelta(hours=12), raw=self.raw(), skip_backtest=True)
        self.assertEqual((self.site / "data/ledger.json").read_text(encoding="utf-8").count("first_predicted_at"),
                         first.count("first_predicted_at"))
        runs = json.loads((self.site / "data/runs.json").read_text(encoding="utf-8"))
        self.assertEqual(len(runs), 2)
        self.assertEqual(len(list((self.site / "archive").glob("*.json"))), 1)  # 同一天只有一份存档

    def test_core_source_failure_fails_closed_and_keeps_old_report_labelled_old(self):
        runmod.run(self.site, NOW, raw=self.raw(), skip_backtest=True)
        good = json.loads((self.site / "latest.json").read_text(encoding="utf-8"))
        bad = self.raw()
        info = bad["sources"]["openfootball:en.1:2026-27"]
        info.update(ok=False, error="HTTP 500")
        bad["by_source"]["openfootball:en.1:2026-27"] = []
        # 不带缓存目录 -> 新站点里没有可降级的缓存
        other = Path(self.tmp.name) / "other" / "fifa"
        (other / "data").mkdir(parents=True)
        (other / "latest.json").write_text(json.dumps(good), encoding="utf-8")
        code = runmod.run(other, NOW + timedelta(days=1), raw=bad, skip_backtest=True)
        self.assertEqual(code, 1)
        st = json.loads((other / "status.json").read_text(encoding="utf-8"))
        self.assertFalse(st["ok"])
        self.assertIn("openfootball:en.1:2026-27", st["error"])
        page = (other / "index.html").read_text(encoding="utf-8")
        self.assertIn("今天没有新报告", page)
        self.assertIn("2026-10-01 的旧报告", page)  # 旧报告被明确标成旧的
        self.assertNotIn("今天的新报告已生成", page)
        self.assertEqual(json.loads((other / "latest.json").read_text(encoding="utf-8"))["report_date"], "2026-10-01")

    def test_failure_after_same_day_success_keeps_today_report_and_explains(self):
        runmod.run(self.site, NOW, raw=self.raw(), skip_backtest=True)
        bad = self.raw()
        bad["sources"]["openfootball:en.1:2026-27"].update(ok=False, error="HTTP 500")
        bad["by_source"]["openfootball:en.1:2026-27"] = []
        (self.site / "data/matches-cache.json.gz").unlink()  # 没有缓存可降级
        code = runmod.run(self.site, NOW + timedelta(hours=12), raw=bad, skip_backtest=True)
        self.assertEqual(code, 1)
        page = (self.site / "index.html").read_text(encoding="utf-8")
        self.assertIn("今天的新报告已生成", page)
        self.assertIn("最近一次刷新失败", page)
        self.assertEqual(json.loads((self.site / "latest.json").read_text(encoding="utf-8"))["report_date"], "2026-10-01")

    def test_failed_source_uses_cache_and_says_so(self):
        runmod.run(self.site, NOW, raw=self.raw(), skip_backtest=True)
        bad = self.raw()
        name = "openfootball:en.1:2026-27"
        bad["sources"][name].update(ok=False, error="timeout")
        bad["by_source"][name] = []
        code = runmod.run(self.site, NOW + timedelta(days=1), raw=bad, skip_backtest=True)
        self.assertEqual(code, 0)
        st = self.status()
        self.assertTrue(any("缓存" in d for d in st["degraded"]))
        self.assertIn("缓存", (self.site / "index.html").read_text(encoding="utf-8"))

    def test_no_previous_report_and_failure_renders_honest_empty_page(self):
        bad = self.raw()
        for n in list(bad["sources"]):
            if n.startswith("openfootball:") and "2026-27" in n:
                bad["sources"][n].update(ok=False, error="down")
        code = runmod.run(self.site, NOW, raw=bad, skip_backtest=True)
        self.assertEqual(code, 1)
        page = (self.site / "index.html").read_text(encoding="utf-8")
        self.assertIn("今天没有新报告", page)
        self.assertIn("还没有任何一份成功生成的报告", page)
        self.assertFalse((self.site / "latest.json").exists())

    def test_missed_days_are_reported_not_backfilled(self):
        runs = [{"at": "x", "date": d, "ok": True, "note": ""} for d in ("2026-09-25", "2026-09-26")]
        strip, missed = runmod.run_strip(runs, "2026-09-30")
        self.assertEqual(missed, ["2026-09-27", "2026-09-28", "2026-09-29"])
        self.assertEqual(len(strip), 14)
        self.assertEqual(strip[-1]["state"], "none")  # 今天还没跑完不算缺

    def test_stale_banner_wiring_present(self):
        runmod.run(self.site, NOW, raw=self.raw(), skip_backtest=True)
        page = (self.site / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="stale"', page)
        self.assertIn('data-stale-h="30"', page)
        self.assertIn(f'data-utc="{NOW.strftime("%Y-%m-%dT%H:%M:%SZ")}"', page)


if __name__ == "__main__":
    unittest.main()
