"""结构性证据采集：选哪几份申报、缓存命中不重复下载、请求硬上限、失败只记数、as_of 之后的申报看不见。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import branch_fixtures as fx
from signal_lattice.evidence.sec_client import SecFetchError
from signal_lattice.evidence.structure_collect import collect_structure, pick_filings
from signal_lattice.evidence.structure_text import ExtractionCache
from signal_lattice.evidence.text_similarity import TextCache

BODY = ("<html><body><p>Item 1A. Risk Factors</p><p>We depend on a single-source supplier for certain key components "
        "used in our devices. Our largest customer accounted for 30% of our total net revenues in fiscal 2025. " +
        "Filler text to make the paragraph long enough for scanning. " * 60 + "</p></body></html>").encode()


class FakeClient:
    def __init__(self, fail_urls=()):
        self.requests_sent = 0
        self.urls = []
        self.fail_urls = set(fail_urls)

    def get_bytes(self, url, cache=True, immutable=False):
        self.requests_sent += 1
        self.urls.append(url)
        if any(f in url for f in self.fail_urls):
            raise SecFetchError("boom")
        return BODY


class PickTests(unittest.TestCase):
    def rows(self):
        return [dict(accession="a-25-1", form="10-K", filed="2025-03-03", report_date="2024-12-31", primary_document="k25.htm"),
                dict(accession="a-26-1", form="10-K", filed="2026-03-02", report_date="2025-12-31", primary_document="k26.htm"),
                dict(accession="a-26-2", form="10-Q", filed="2026-05-05", report_date="2026-03-31", primary_document="q1.htm"),
                dict(accession="a-26-3", form="10-Q", filed="2026-08-04", report_date="2026-06-30", primary_document="q2.htm"),
                dict(accession="a-26-4", form="10-Q", filed="2026-08-05", report_date="2026-06-30", primary_document="")]

    def test_latest_annual_plus_newer_latest_quarterly_with_a_document(self):
        self.assertEqual([r["accession"] for r in pick_filings(self.rows())], ["a-26-1", "a-26-3"])

    def test_quarterly_older_than_the_annual_is_not_picked(self):
        rows = [r for r in self.rows() if r["accession"] in ("a-25-1", "a-26-1")] + [
            dict(accession="a-25-9", form="10-Q", filed="2025-11-04", report_date="2025-09-30", primary_document="q3.htm")]
        self.assertEqual([r["accession"] for r in pick_filings(rows)], ["a-26-1"])

    def test_no_annual_uses_only_the_newest_quarterly(self):
        rows = [r for r in self.rows() if r["form"] == "10-Q"]
        self.assertEqual([r["accession"] for r in pick_filings(rows)], ["a-26-3"])


class CollectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.tc, self.ec = TextCache(root / "text"), ExtractionCache(root / "ext")
        self.store = fx.build_store()

    def tearDown(self):
        self.tmp.cleanup()

    def run_collect(self, client, as_of="2026-09-15", **kw):
        return collect_structure(client, self.store, [fx.CIK], as_of, self.tc, self.ec, log=lambda m: None, **kw)

    def test_extracts_and_then_serves_everything_from_cache_without_new_requests(self):
        client = FakeClient()
        first = self.run_collect(client)
        self.assertEqual(first["stats"]["fetched"], 2)            # FY2025 10-K + 之后更新的 10-Q
        self.assertEqual(client.requests_sent, 2)
        kinds = {i.kind for f in first["by_cik"][fx.CIK] for i in f.items}
        self.assertIn("sole_source", kinds)
        self.assertIn("customer_concentration", kinds)
        second = self.run_collect(client)
        self.assertEqual((second["stats"]["cached"], second["stats"]["requests"]), (2, 0))   # 同一天重跑：零请求
        self.assertEqual(client.requests_sent, 2)

    def test_reextraction_uses_text_cache_not_the_network(self):
        client = FakeClient()
        self.run_collect(client)
        for path in self.ec.directory.glob("*.json.gz"):
            path.unlink()                                          # 抽取器升级：抽取缓存作废，正文缓存还在
        again = self.run_collect(client)
        self.assertEqual((again["stats"]["from_text_cache"], again["stats"]["requests"]), (2, 0))

    def test_filings_after_as_of_are_invisible(self):
        client = FakeClient()
        result = self.run_collect(client, as_of="2026-07-15")      # H1'26 10-Q 2026-08-04 还没申报
        accessions = {f.accession for f in result["by_cik"][fx.CIK]}
        self.assertEqual(accessions, {fx.ACC[("2025-12-31", "10-K")], fx.ACC[("2026-03-31", "10-Q")]})
        self.assertTrue(all(f.filed <= "2026-07-15" for f in result["by_cik"][fx.CIK]))

    def test_request_cap_and_failures_are_counted_not_raised(self):
        capped = self.run_collect(FakeClient(), max_requests=1)
        self.assertEqual((capped["stats"]["fetched"], capped["stats"]["skipped_by_cap"]), (1, 1))
        failing = self.run_collect(FakeClient(fail_urls=["doc0021"]), max_requests=5)   # 10-Q 的主文档下载失败
        self.assertEqual(failing["stats"]["failed"], 1)


if __name__ == "__main__":
    unittest.main()
