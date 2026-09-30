"""分支共用零件：阶梯评分、维度归一与覆盖率、参数校验、关键词标记、companyfacts 裁剪与限量入账。"""

from __future__ import annotations

import unittest

from signal_lattice.branches import sec_inputs
from signal_lattice.branches import textmarkers as TM
from signal_lattice.branches.fundamentals import NEEDED_CONCEPTS
from signal_lattice.branches.scoring_support import (NO_EVIDENCE, EvidenceRef, FactorResult, ParamsError, aggregate_dimension,
                                                     check_table, geometric_mean, no_evidence, table_rating)
from signal_lattice.evidence.factstore import FactStore
from signal_lattice.evidence.sec_client import SecNotFound


class TableRatingTests(unittest.TestCase):
    HIGHER = {"direction": "higher", "cuts": [[0.3, 4], [0.1, 3], [0.0, 2]], "floor": 0}
    LOWER = {"direction": "lower", "cuts": [[0.15, 5], [0.5, 3]], "floor": 0}

    def test_higher_and_lower_boundaries_are_inclusive(self):
        self.assertEqual([table_rating(v, self.HIGHER) for v in (0.5, 0.3, 0.29, 0.1, 0.0, -0.01)], [4, 4, 3, 3, 2, 0])
        self.assertEqual([table_rating(v, self.LOWER) for v in (0.0, 0.15, 0.16, 0.5, 0.51)], [5, 5, 3, 3, 0])

    def test_none_and_nan_give_none_not_a_rating(self):
        self.assertIsNone(table_rating(None, self.HIGHER))
        self.assertIsNone(table_rating(float("nan"), self.HIGHER))

    def test_check_table_rejects_bad_shapes(self):
        check_table(self.HIGHER, "t")
        for bad in ({"direction": "up", "cuts": [[1, 1]], "floor": 0},
                    {"direction": "higher", "cuts": [], "floor": 0},
                    {"direction": "higher", "cuts": [[1, 1], [1, 2]], "floor": 0},
                    {"direction": "higher", "cuts": [[1, 5], [2, 1]], "floor": 0},   # 阈值大者评分低：不单调
                    {"direction": "higher", "cuts": [[1, 1]], "floor": 3},
                    {"direction": "higher", "cuts": [[1]], "floor": 0}):
            with self.assertRaises(ParamsError):
                check_table(bad, "t")


class AggregateTests(unittest.TestCase):
    W = {"a": 50, "b": 30, "c": 20}

    def factors(self, a=5.0, b=None, c=5.0):
        out = {}
        for name, r in (("a", a), ("b", b), ("c", c)):
            out[name] = FactorResult(name, r, "x") if r is not None else no_evidence(name, "n/a")
        return out

    def test_only_observed_factors_are_averaged_and_coverage_reported(self):
        d = aggregate_dimension("d", self.factors(a=5.0, b=None, c=0.0), self.W, 5.0, 0.5, ["a"])
        self.assertAlmostEqual(d.score, 50 / 70 * 100)          # (5/5×50 + 0/5×20) / 70
        self.assertAlmostEqual(d.coverage, 0.7)
        self.assertTrue(d.verifiable)
        self.assertEqual(d.no_evidence, ("b",))

    def test_zero_rating_is_observed_not_missing(self):
        d = aggregate_dimension("d", self.factors(a=0.0, b=0.0, c=0.0), self.W, 5.0, 0.5, [])
        self.assertEqual((d.score, d.coverage), (0.0, 1.0))

    def test_coverage_floor_and_required_factor_make_the_dimension_unverifiable(self):
        low = aggregate_dimension("d", self.factors(a=None, b=None, c=5.0), self.W, 5.0, 0.5, [])
        self.assertFalse(low.verifiable)
        self.assertTrue(low.reason.startswith("COVERAGE_BELOW_FLOOR"))
        req = aggregate_dimension("d", self.factors(a=None, b=5.0, c=5.0), self.W, 5.0, 0.1, ["a"])
        self.assertFalse(req.verifiable)
        self.assertEqual(req.reason, "REQUIRED_FACTOR_NO_EVIDENCE:a")
        none = aggregate_dimension("d", self.factors(a=None, b=None, c=None), self.W, 5.0, 0.0, [])
        self.assertEqual((none.score, none.reason), (None, "NO_FACTOR_OBSERVED"))

    def test_geometric_mean_collapses_on_a_near_zero_dimension(self):
        self.assertAlmostEqual(geometric_mean([80, 80, 80, 80, 80]), 80)
        self.assertLess(geometric_mean([80, 80, 80, 80, 0]), 20)   # 一维近零，整体塌陷（不可补偿）
        self.assertAlmostEqual(geometric_mean([0, 0]), 0.01)

    def test_evidence_ref_primary_link_rules(self):
        sec = EvidenceRef("xbrl", "x", 1.0, "0001-26-000001", "10-K", "2026-01-01", "2025-12-31",
                          "https://www.sec.gov/Archives/edgar/data/1/000126000001/x.htm")
        self.assertTrue(sec.is_primary_link)
        self.assertFalse(EvidenceRef("market", "q", 1.0, url="https://www.sec.gov/x").is_primary_link)
        self.assertFalse(EvidenceRef("xbrl", "x", 1.0, url="https://example.com/x").is_primary_link)
        self.assertFalse(EvidenceRef("xbrl", "x", 1.0).is_primary_link)


class TextMarkerTests(unittest.TestCase):
    def test_six_owner_phrases_are_counted(self):
        text = ("We rely on a sole source supplier. Certain parts are single-sourced. We are capacity constrained and "
                "lead times have lengthened. Our backlog grew. Products are on allocation. Supplier allocations continue. "
                "Long lead times persist. Asset allocation is unrelated.")
        counts, snippets = TM.scan_text(text)
        self.assertEqual(counts["sole_source"], 2)
        self.assertEqual(counts["capacity_constrained"], 1)
        self.assertEqual(counts["lead_times"], 2)
        self.assertEqual(counts["backlog"], 1)
        self.assertEqual(counts["allocation"], 2)   # on allocation + supplier allocations；「asset allocation」不算
        self.assertIn("sole source", snippets["sole_source"][0].lower())

    def test_html_is_stripped(self):
        html = "<html><style>.a{}</style><body><p>Lead&nbsp;times &amp; <b>backlog</b></p><script>var lead_times=1</script></body></html>"
        self.assertEqual(TM.html_to_text(html), "Lead times & backlog")
        self.assertNotIn("var", TM.html_to_text(html))
        counts, _ = TM.scan_text(TM.html_to_text(html))
        self.assertEqual((counts["lead_times"], counts["backlog"]), (1, 1))

    def test_present_needs_two_mentions(self):
        m = TM.TextMarkers(1, "0001-26-000001", "10-K", "2026-03-01", "2025-12-31", "https://www.sec.gov/x", 10,
                           {"sole_source": 1, "lead_times": 2, "backlog": 0}, {})
        self.assertFalse(m.present("sole_source"))
        self.assertTrue(m.present("lead_times"))
        self.assertEqual(m.groups_present(), ("lead_times",))
        self.assertTrue(m.ref("lead_times").is_primary_link)
        self.assertEqual(TM.TextMarkers.from_dict(m.to_dict()).counts, m.counts)

    def test_latest_document_prefers_a_recent_annual_report(self):
        store = FactStore(":memory:")
        store.ingest_submissions(1, {"filings": {"recent": {
            "accessionNumber": ["a", "b", "c"], "form": ["10-K", "10-Q", "10-Q"],
            "filingDate": ["2026-03-01", "2026-05-01", "2026-08-01"], "reportDate": ["2025-12-31", "2026-03-31", "2026-06-30"],
            "primaryDocument": ["k.htm", "q1.htm", "q2.htm"], "items": ["", "", ""]}}}, "2026-09-01")
        self.assertEqual(TM.latest_periodic_with_document(store, 1, "2026-09-01")["accession"], "a")   # 年报 ≤200 天内
        self.assertEqual(TM.latest_periodic_with_document(store, 1, "2026-05-15")["accession"], "a")
        self.assertIsNone(TM.latest_periodic_with_document(store, 1, "2026-01-01"))                       # 当时还没有申报


class SecInputsTests(unittest.TestCase):
    def test_prune_keeps_only_needed_concepts(self):
        payload = {"cik": 1, "entityName": "X", "facts": {
            "us-gaap": {"Revenues": {"units": {"USD": []}}, "SomethingElse": {"units": {"USD": []}}},
            "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": []}}, "Other": {"units": {}}}}}
        pruned = sec_inputs.prune_companyfacts(payload)
        self.assertEqual(set(pruned["facts"]["us-gaap"]), {"Revenues"})
        self.assertEqual(set(pruned["facts"]["dei"]), {"EntityCommonStockSharesOutstanding"})
        self.assertEqual(pruned["entityName"], "X")
        self.assertIn("us-gaap:RevenueRemainingPerformanceObligation", NEEDED_CONCEPTS)
        self.assertIn("us-gaap:PaymentsToAcquirePropertyPlantAndEquipment", NEEDED_CONCEPTS)

    def test_collect_is_resumable_capped_and_counts_failures(self):
        class Fake:
            requests_sent = 0
            calls = []

            def companyfacts(self, cik):
                Fake.calls.append(cik)
                if cik == 3:
                    raise SecNotFound("HTTP_404")
                return {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
                    {"start": "2025-01-01", "end": "2025-12-31", "val": 1.0, "accn": "0000000000-26-000001", "form": "10-K",
                     "filed": "2026-02-01"}]}}}}}

        store = FactStore(":memory:")
        stats = sec_inputs.collect_companyfacts(Fake(), store, [1, 2, 3], "2026-09-01", workers=1, log=lambda m: None)
        self.assertEqual(stats, {"ingested": 2, "skipped": 0, "not_found": 1, "failed": 0})
        Fake.calls.clear()
        stats = sec_inputs.collect_companyfacts(Fake(), store, [1, 2, 3, 4], "2026-09-01", workers=1, log=lambda m: None)
        self.assertEqual(Fake.calls, [3, 4])          # 已入账的 1、2 不再请求（3 上次 404 没入账，重试一次）
        self.assertEqual(stats["skipped"], 2)
        Fake.calls.clear()
        stats = sec_inputs.collect_companyfacts(Fake(), store, [10, 11, 12, 13], "2026-09-01", workers=1,
                                                log=lambda m: None, max_requests=2)
        self.assertEqual(len(Fake.calls), 2)          # 请求硬上限


if __name__ == "__main__":
    unittest.main()
