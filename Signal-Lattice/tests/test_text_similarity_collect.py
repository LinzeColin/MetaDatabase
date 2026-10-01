"""Lazy Prices 研究层每轮增量生成：记录带链接与申报日、时点正确、单轮请求上限分批补齐、已算过的不重下、失败不无限占额度。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from signal_lattice import research_cycle as RC  # noqa: E402
from signal_lattice.evidence import text_similarity as ts  # noqa: E402
from signal_lattice.evidence.eventstore import EventStore  # noqa: E402
from signal_lattice.evidence.factstore import FactStore  # noqa: E402
from signal_lattice.evidence.sec_client import SecFetchError  # noqa: E402
from test_text_similarity import RISK_NEW_CHANGED, RISK_OLD  # noqa: E402
from test_text_similarity import filing_html as _filing_html  # noqa: E402


def filing_html(risk):
    # 正文至少 2000 字符才算有效申报（fetch_text 的下限）
    return _filing_html(risk, business="The company designs and sells industrial widgets to distributors across North America. " * 30)


class FakeClient:
    """按 URL 返回合成申报；记录请求数。missing 里的文档抛 SecFetchError。"""

    def __init__(self, bodies, missing=()):
        self.bodies, self.missing, self.requests_sent, self.urls = bodies, set(missing), 0, []

    def get_bytes(self, url, cache=True, immutable=False):
        self.requests_sent += 1
        self.urls.append(url)
        if any(m in url for m in self.missing):
            raise SecFetchError("404")
        return self.bodies[url.rsplit("/", 1)[1]]


def submissions(rows):
    return {"name": "X", "tickers": ["X"], "exchanges": ["Nasdaq"], "sic": "3570", "filings": {"recent": {
        "accessionNumber": [r[0] for r in rows], "form": [r[1] for r in rows], "filingDate": [r[2] for r in rows],
        "reportDate": [r[3] for r in rows], "primaryDocument": [r[4] for r in rows], "items": ["" for _ in rows]}}}


def entry(cik, symbol):
    return {"cik": cik, "symbol": symbol, "name": symbol + " Inc", "market_cap_usd": 1e9 + cik, "exchange": "NASDAQ"}


class CollectRecordsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.facts, self.events = FactStore(self.tmp / "f.sqlite"), EventStore(self.tmp / "e.sqlite")
        self.cache = ts.TextCache(self.tmp / "text")
        self.bodies = {}
        self.entries = []

    def tearDown(self):
        self.facts.close()
        self.events.close()

    def company(self, cik, symbol, changed=False):
        """每家两份 10-K：2025-02 的旧版、2026-02 的新版（changed = 新版风险因素大改）。"""
        old, new = "old%d.htm" % cik, "new%d.htm" % cik
        self.bodies[old] = filing_html(RISK_OLD)
        self.bodies[new] = filing_html(RISK_NEW_CHANGED if changed else RISK_OLD)
        self.facts.ingest_submissions(cik, submissions([
            ("0000000000-25-%06d" % cik, "10-K", "2025-02-20", "2024-12-31", old),
            ("0000000000-26-%06d" % cik, "10-K", "2026-02-20", "2025-12-31", new)]), date(2026, 9, 1))
        self.entries.append(entry(cik, symbol))

    def collect(self, client, as_of=date(2026, 9, 1), max_requests=1000, entries=None):
        return ts.collect_records(client, self.events, self.facts, self.cache, entries or self.entries, as_of,
                                  max_requests=max_requests, workers=1, log=lambda m: None)

    def test_records_carry_sec_links_filed_dates_and_percentiles(self):
        for cik, symbol, changed in [(1, "AAA", False), (2, "BBB", True), (3, "CCC", False), (4, "DDD", False), (5, "EEE", False), (6, "FFF", False)]:
            self.company(cik, symbol, changed)
        result = self.collect(FakeClient(self.bodies))
        by = {r["symbol"]: r for r in result["records"]}
        self.assertEqual(sorted(by), ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"])
        b = by["BBB"]
        self.assertEqual((b["filed"], b["prior_filed"], b["form"]), ("2026-02-20", "2025-02-20", "10-K"))
        self.assertEqual(b["url"], "https://www.sec.gov/Archives/edgar/data/2/000000000026000002/new2.htm")
        self.assertEqual(b["prior_url"], "https://www.sec.gov/Archives/edgar/data/2/000000000025000002/old2.htm")
        self.assertLess(b["similarity"], by["AAA"]["similarity"])
        self.assertTrue(b["big_changer"])
        self.assertAlmostEqual(b["percentile"], 1 / 6)                           # 6 家里最不相似 = 最低分位
        self.assertEqual(result["coverage"]["computed"], 6)
        self.assertEqual(result["coverage"]["pool"], 6)

    def test_only_filings_public_at_as_of_are_used(self):
        self.company(1, "AAA", changed=True)
        early = self.collect(FakeClient(self.bodies), as_of=date(2026, 1, 31))     # 新 10-K 2026-02-20 还没公开：没有可比的一对
        self.assertEqual(early["records"], [])
        self.assertEqual(early["coverage"]["no_comparable_pair"], 1)
        later = self.collect(FakeClient(self.bodies), as_of=date(2026, 2, 20))
        self.assertEqual([r["filed"] for r in later["records"]], ["2026-02-20"])

    def test_request_cap_defers_the_rest_and_next_run_finishes_without_redownloading(self):
        for cik in range(1, 7):
            self.company(cik, "S%d" % cik)
        client = FakeClient(self.bodies)
        first = self.collect(client, max_requests=6)                             # 每家 2 份正文：本轮只够 3 家
        self.assertEqual(first["coverage"]["computed_this_run"], 3)
        self.assertEqual(first["coverage"]["deferred_by_request_cap"], 3)
        self.assertLessEqual(client.requests_sent, 6)
        second = self.collect(client, max_requests=6)
        self.assertEqual(second["coverage"]["computed"], 6)
        self.assertEqual(second["coverage"]["reused"], 3)
        self.assertEqual(client.requests_sent, 12)                                # 每份正文只下载一次
        third = self.collect(client, max_requests=6)
        self.assertEqual(client.requests_sent, 12)                               # 已算过的不再请求
        self.assertEqual(third["coverage"]["reused"], 6)
        self.assertEqual(third["records"], second["records"])                    # 幂等：内容不变，快照 hash 不会无谓变化

    def test_companies_without_any_record_go_first_and_cached_text_costs_nothing(self):
        for cik in range(1, 4):
            self.company(cik, "S%d" % cik)
        self.cache.put("0000000000-25-000001", "x" * 3000)                      # 空壳占位；真实正文下面覆盖
        self.cache.put("0000000000-25-000001", ts.html_to_text(self.bodies["old1.htm"]))
        self.cache.put("0000000000-26-000001", ts.html_to_text(self.bodies["new1.htm"]))
        client = FakeClient(self.bodies)
        result = self.collect(client, max_requests=0)                            # 额度为 0：只有正文已缓存的公司能算
        self.assertEqual([r["symbol"] for r in result["records"]], ["S1"])
        self.assertEqual(client.requests_sent, 0)

    def test_offline_uses_only_cached_text_and_sends_nothing(self):
        self.company(1, "AAA")
        result = self.collect(None)
        self.assertEqual(result["records"], [])
        self.assertEqual(result["coverage"]["max_requests_per_run"], 0)

    def test_unfetchable_filing_stops_consuming_budget_after_three_tries(self):
        self.company(1, "AAA")
        client = FakeClient(self.bodies, missing=["new1.htm"])
        for _ in range(ts.TEXT_SIM_MAX_TRIES):
            result = self.collect(client)
            self.assertEqual(result["coverage"]["failed_this_run"], 1)
        before = client.requests_sent
        result = self.collect(client)
        self.assertEqual(result["coverage"]["gave_up"], 1)
        self.assertEqual(client.requests_sent, before)

    def test_a_new_filing_is_recomputed_and_old_record_is_not_reused_for_it(self):
        self.company(1, "AAA")
        client = FakeClient(self.bodies)
        self.collect(client)
        self.bodies["q.htm"] = filing_html(RISK_OLD)
        self.bodies["q0.htm"] = filing_html(RISK_NEW_CHANGED)
        self.facts.ingest_submissions(1, submissions([
            ("0000000000-25-900001", "10-Q", "2025-08-01", "2025-06-30", "q0.htm"),
            ("0000000000-26-900002", "10-Q", "2026-08-01", "2026-06-30", "q.htm")]), date(2026, 9, 1))
        result = self.collect(client)
        record = result["records"][0]
        self.assertEqual((record["form"], record["filed"]), ("10-Q", "2026-08-01"))
        self.assertEqual(result["coverage"]["computed_this_run"], 1)


class ResearchCycleHookTests(unittest.TestCase):
    def test_live_hook_writes_the_records_file_and_returns_snapshot_records_without_sections(self):
        tmp = Path(tempfile.mkdtemp())
        cfg = RC.CycleConfig(project_root=ROOT, work_dir=tmp, out_dir=tmp / "out", facts_db=tmp / "f", events_db=tmp / "e",
                             bars_dir=tmp / "b", text_cache_dir=tmp / "t", structure_cache_dir=tmp / "s", sec_cache_dir=tmp / "c")
        record = {"symbol": "AAA", "filed": "2026-02-20", "sections": {"x": 1}, "url": "u", "percentile": 0.5}
        fake = {"records": [record], "thresholds": {"10-K": 0.9}, "coverage": {"computed": 1}}
        with mock.patch.object(ts, "collect_records", return_value=fake):
            out = RC.LiveHooks()._text_similarity(cfg, None, None, None, None, [], date(2026, 9, 1), lambda m: None)
        self.assertNotIn("sections", out["records"][0])
        self.assertEqual(out["records"][0]["url"], "u")
        written = json.loads((tmp / "text-similarity" / "text-similarity-2026-09-01.json").read_text("utf-8"))
        self.assertIn("sections", written["records"][0])                       # 落盘文件保留完整比对（事件航图报告读它）
        self.assertEqual(out["source_file"], "text-similarity-2026-09-01.json")

    def test_explicit_records_file_still_wins(self):
        tmp = Path(tempfile.mkdtemp())
        path = tmp / "given.json"
        path.write_text(json.dumps({"coverage": {"computed": 1}, "thresholds": {}, "records": [{"symbol": "Z", "sections": {}}]}), "utf-8")
        cfg = RC.CycleConfig(project_root=ROOT, work_dir=tmp, out_dir=tmp, facts_db=tmp / "f", events_db=tmp / "e", bars_dir=tmp / "b",
                             text_cache_dir=tmp / "t", structure_cache_dir=tmp / "s", sec_cache_dir=tmp / "c", text_similarity_path=path)
        with mock.patch.object(ts, "collect_records") as collect:
            out = RC.LiveHooks()._text_similarity(cfg, None, None, None, None, [], date(2026, 9, 1), lambda m: None)
        collect.assert_not_called()
        self.assertEqual(out["records"], [{"symbol": "Z"}])


if __name__ == "__main__":
    unittest.main()
