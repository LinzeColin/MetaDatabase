"""事实库：按申报日入账、重述不覆盖原值、点时查询只看 as_of 之前的申报。"""

from __future__ import annotations

import unittest
from datetime import date

from signal_lattice.evidence import FactStore


def companyfacts(entries, concept="Revenues", unit="USD"):
    return {"facts": {"us-gaap": {concept: {"units": {unit: entries}}}}}


def entry(val, end, accn, filed, start="2023-01-01", form="10-K"):
    row = {"val": val, "end": end, "accn": accn, "filed": filed, "form": form}
    if start:
        row["start"] = start
    return row


class FactStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = FactStore(":memory:")
        self.addCleanup(self.store.close)

    def test_restatement_is_stored_beside_original_not_over_it(self):
        payload = companyfacts([
            entry(100, "2023-12-31", "0000000001-24-000001", "2024-02-20"),
            entry(90, "2023-12-31", "0000000001-25-000002", "2025-02-20"),  # 次年 10-K 里的重述
        ])
        self.assertEqual(self.store.ingest_companyfacts(7, payload, date(2025, 3, 1)), 2)
        versions = self.store.all_versions(7, "us-gaap:Revenues")
        self.assertEqual([(v.value, v.filed) for v in versions], [(100.0, "2024-02-20"), (90.0, "2025-02-20")])

    def test_as_of_before_restatement_sees_original_value(self):
        self.store.ingest_companyfacts(7, companyfacts([
            entry(100, "2023-12-31", "0000000001-24-000001", "2024-02-20"),
            entry(90, "2023-12-31", "0000000001-25-000002", "2025-02-20"),
        ]), date(2025, 3, 1))
        before = self.store.facts_as_of(7, "us-gaap:Revenues", "2025-02-19")
        after = self.store.facts_as_of(7, "us-gaap:Revenues", "2025-02-20")
        self.assertEqual([f.value for f in before], [100.0])
        self.assertEqual([f.value for f in after], [90.0])  # 同期取 filed 最新的一条，且只有一条

    def test_as_of_never_returns_a_filing_made_after_it(self):
        self.store.ingest_companyfacts(7, companyfacts([
            entry(100, "2023-12-31", "0000000001-24-000001", "2024-02-20"),
            entry(120, "2024-12-31", "0000000001-25-000002", "2025-02-20", start="2024-01-01"),
        ]), date(2025, 3, 1))
        self.assertEqual(self.store.facts_as_of(7, "us-gaap:Revenues", "2024-02-19"), [])
        visible = self.store.facts_as_of(7, "us-gaap:Revenues", "2024-06-30")
        self.assertEqual([f.period_end for f in visible], ["2023-12-31"])
        self.assertTrue(all(f.filed <= "2024-06-30" for f in visible))
        self.assertTrue(all(f.filed <= "2099-01-01" for f in self.store.facts_as_of(7, "us-gaap:Revenues", date(2099, 1, 1))))

    def test_different_periods_all_returned_and_ordered(self):
        self.store.ingest_companyfacts(7, companyfacts([
            entry(120, "2024-12-31", "0000000001-25-000002", "2025-02-20", start="2024-01-01"),
            entry(100, "2023-12-31", "0000000001-24-000001", "2024-02-20"),
        ]), date(2025, 3, 1))
        facts = self.store.facts_as_of(7, "us-gaap:Revenues", "2025-12-31")
        self.assertEqual([f.period_end for f in facts], ["2023-12-31", "2024-12-31"])

    def test_ingest_is_idempotent_and_instant_facts_have_no_start(self):
        payload = companyfacts([entry(5_000_000, "2024-06-30", "0000000001-24-000009", "2024-07-30", start=None, form="10-Q")],
                               concept="EntityCommonStockSharesOutstanding", unit="shares")
        payload["facts"]["dei"] = payload["facts"].pop("us-gaap")
        self.assertEqual(self.store.ingest_companyfacts(7, payload, date(2024, 8, 1)), 1)
        self.assertEqual(self.store.ingest_companyfacts(7, payload, date(2024, 8, 2)), 0)
        fact = self.store.facts_as_of(7, "dei:EntityCommonStockSharesOutstanding", "2024-08-01")[0]
        self.assertIsNone(fact.period_start)
        self.assertEqual(fact.source_url, "https://www.sec.gov/Archives/edgar/data/7/000000000124000009/0000000001-24-000009-index.htm")
        self.assertEqual((fact.cik, fact.unit, fact.form, fact.accession), (7, "shares", "10-Q", "0000000001-24-000009"))

    def test_instant_fact_restatement_also_kept(self):
        base = dict(start=None, form="10-Q")
        self.store.ingest_companyfacts(7, companyfacts([
            entry(10, "2024-06-30", "0000000001-24-000009", "2024-07-30", **base),
            entry(11, "2024-06-30", "0000000001-24-000010", "2024-08-15", **base),
        ], concept="Assets"), date(2024, 9, 1))
        self.assertEqual(len(self.store.all_versions(7, "us-gaap:Assets")), 2)
        self.assertEqual(self.store.facts_as_of(7, "us-gaap:Assets", "2024-08-01")[0].value, 10.0)
        self.assertEqual(self.store.facts_as_of(7, "us-gaap:Assets", "2024-08-15")[0].value, 11.0)

    def test_delisted_and_renamed_entities_are_never_deleted(self):
        self.store.upsert_listed([{"cik": 7, "name": "OLD NAME INC", "ticker": "OLD", "exchange": "Nasdaq"}], date(2024, 1, 1))
        # 之后的名单里这家不在了（退市），另一家出现；旧行必须还在
        self.store.upsert_listed([{"cik": 8, "name": "OTHER CO", "ticker": "OTH", "exchange": "NYSE"}], date(2025, 1, 1))
        self.store.ingest_submissions(7, {"name": "NEW NAME CORP", "tickers": ["NEW"], "exchanges": ["Nasdaq"],
                                          "formerNames": [{"name": "OLD NAME INC"}], "filings": {"recent": {}}}, date(2025, 2, 1))
        self.assertEqual(self.store.count("entities"), 2)
        names = {n["name"] for n in self.store.entity_names(7)}
        self.assertEqual(names, {"OLD NAME INC", "NEW NAME CORP"})

    def test_submissions_filings_are_point_in_time(self):
        recent = {"accessionNumber": ["0000000001-24-000001", "0000000001-25-000002"], "form": ["8-K", "4"],
                  "filingDate": ["2024-05-01", "2025-05-01"], "reportDate": ["2024-04-30", ""],
                  "items": ["1.01", ""], "primaryDocument": ["a.htm", "xslF345X05/wk-form4.xml"]}
        self.assertEqual(self.store.ingest_submissions(7, {"name": "X", "filings": {"recent": recent}}, date(2025, 6, 1)), 2)
        self.assertEqual([f["form"] for f in self.store.filings_as_of(7, "2024-12-31")], ["8-K"])
        self.assertEqual([f["form"] for f in self.store.filings_as_of(7, "2025-12-31", forms=["4"])], ["4"])

    def test_bad_as_of_string_is_rejected(self):
        with self.assertRaises(ValueError):
            self.store.facts_as_of(7, "us-gaap:Revenues", "2024-02-30 OR 1=1")


if __name__ == "__main__":
    unittest.main()
