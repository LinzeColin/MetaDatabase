"""Lazy Prices 文本比对：HTML 去标签、余弦相似度、风险因素段定位、新段落、大改动者分位、选同类申报。"""

from __future__ import annotations

import unittest

from signal_lattice.evidence import text_similarity as ts

RISK_OLD = ("We depend on a single supplier for our key component and any interruption would harm our business materially. " * 3)
RISK_NEW_SAME = RISK_OLD
RISK_NEW_CHANGED = ("We received a subpoena from the Department of Justice regarding our billing practices and a cybersecurity "
                    "incident exposed customer data which may result in class action litigation and regulatory fines going forward. " * 3)


def filing_html(risk_body: str, legal_body: str = "There are no material pending legal proceedings against the company at this time. " * 3,
                business: str = "The company designs and sells industrial widgets to distributors across North America. " * 8):
    return ("<html><head><title>10-K</title><style>p{color:red}</style></head><body>"
            "<ix:header><ix:hidden>HIDDENFACT 12345</ix:hidden></ix:header>"
            "<p>TABLE OF CONTENTS</p><p>Item 1A. Risk Factors 12</p><p>Item 1B. Unresolved Staff Comments 20</p>"
            "<p>Item 1. Business</p><p>%s</p>"
            "<div>Item 1A.</div><div>Risk Factors</div><p>%s</p><p>%s</p>"
            "<p>Item 1B. Unresolved Staff Comments</p><p>None.</p><p>Item 2. Properties</p><p>We lease offices.</p>"
            "<p>Item 3. Legal Proceedings</p><p>%s</p><p>Item 4. Mine Safety Disclosures</p><p>Not applicable.</p>"
            "</body></html>" % (business, risk_body, "Additional general risk language about competition and pricing pressure. " * 4, legal_body)).encode()


class TextTests(unittest.TestCase):
    def test_html_to_text_drops_tags_hidden_facts_and_keeps_paragraphs(self):
        text = ts.html_to_text(filing_html(RISK_OLD))
        self.assertNotIn("<p>", text)
        self.assertNotIn("HIDDENFACT", text)
        self.assertNotIn("color:red", text)
        self.assertIn("Item 1A.\nRisk Factors", text)
        self.assertGreater(text.count("\n"), 8)

    def test_cosine_identical_disjoint_and_partial(self):
        a = ts.tf_vector("the quick brown fox jumps over the lazy dog")
        self.assertAlmostEqual(ts.cosine(a, a), 1.0)
        self.assertEqual(ts.cosine(a, ts.tf_vector("completely different words entirely here")), 0.0)
        partial = ts.cosine(a, ts.tf_vector("the quick brown cat sits under the busy tree"))
        self.assertTrue(0.2 < partial < 0.8)
        self.assertEqual(ts.cosine(ts.tf_vector(""), a), 0.0)

    def test_numbers_and_punctuation_do_not_change_similarity(self):
        a = ts.tf_vector("Revenue was $12,345 thousand in fiscal 2025, up 12.5%.")
        b = ts.tf_vector("Revenue was $99,999 thousand in fiscal 2026, up 3.1%.")
        self.assertAlmostEqual(ts.cosine(a, b), 1.0)

    def test_risk_section_takes_the_body_not_the_table_of_contents(self):
        text = ts.html_to_text(filing_html(RISK_OLD))
        section = ts.extract_section(text, "risk_factors")
        self.assertIn("single supplier", section)
        self.assertNotIn("Unresolved Staff Comments 20", section)
        self.assertIn("no material pending legal", ts.extract_section(text, "legal_proceedings"))

    def test_unchanged_filing_is_near_identical(self):
        old = ts.html_to_text(filing_html(RISK_OLD))
        result = ts.compare_documents(ts.html_to_text(filing_html(RISK_NEW_SAME)), old)
        self.assertGreater(result["similarity"], 0.999)
        self.assertEqual(result["sections"]["risk_factors"]["new_paragraphs"], 0)
        self.assertIsNone(result["largest_change_section"])        # 没有变化就不报「变化最大的段落」

    def test_changed_risk_factors_are_detected_with_the_new_paragraph(self):
        old = ts.html_to_text(filing_html(RISK_OLD))
        new = ts.html_to_text(filing_html(RISK_NEW_CHANGED))
        same = ts.compare_documents(ts.html_to_text(filing_html(RISK_NEW_SAME)), old)
        result = ts.compare_documents(new, old)
        self.assertLess(result["similarity"], same["similarity"])
        risk = result["sections"]["risk_factors"]
        self.assertGreater(risk["new_paragraph_share"], 0.3)
        self.assertIn("subpoena", risk["sample_new_paragraph"])
        self.assertEqual(result["largest_change_section"], "风险因素（Item 1A）")
        self.assertIn("subpoena", result["largest_change_excerpt"])

    def test_missing_sections_do_not_crash(self):
        result = ts.compare_documents("plain text without headings " * 50, "other plain text " * 50)
        self.assertFalse(result["sections"]["risk_factors"]["found"])
        self.assertIsNone(result["largest_change_section"])


def meta(accession, form, filed, report, primary="a.htm"):
    return {"accession": accession, "form": form, "filed": filed, "report_date": report, "primary_document": primary}


class PairTests(unittest.TestCase):
    def test_10k_pairs_with_previous_10k(self):
        rows = [meta("k1", "10-K", "2024-03-01", "2023-12-31"), meta("q1", "10-Q", "2024-05-01", "2024-03-31"),
                meta("k2", "10-K", "2025-03-01", "2024-12-31")]
        latest, previous = ts.pick_pair(rows, "2025-06-01")
        self.assertEqual((latest["accession"], previous["accession"]), ("k2", "k1"))

    def test_10q_pairs_with_same_quarter_last_year_not_the_previous_quarter(self):
        rows = [meta("q1-24", "10-Q", "2024-05-01", "2024-03-31"), meta("q2-24", "10-Q", "2024-08-01", "2024-06-30"),
                meta("k", "10-K", "2025-03-01", "2024-12-31"), meta("q1-25", "10-Q", "2025-05-01", "2025-03-31")]
        latest, previous = ts.pick_pair(rows, "2025-06-01")
        self.assertEqual((latest["accession"], previous["accession"]), ("q1-25", "q1-24"))

    def test_as_of_hides_the_newer_filing(self):
        rows = [meta("k1", "10-K", "2024-03-01", "2023-12-31"), meta("k2", "10-K", "2025-03-01", "2024-12-31"),
                meta("k3", "10-K", "2026-03-01", "2025-12-31")]
        latest, previous = ts.pick_pair(rows, "2025-06-01")
        self.assertEqual((latest["accession"], previous["accession"]), ("k2", "k1"))

    def test_no_prior_comparable_filing_gives_none(self):
        self.assertIsNone(ts.pick_pair([meta("k1", "10-K", "2025-03-01", "2024-12-31")], "2025-06-01"))
        self.assertIsNone(ts.pick_pair([meta("q1", "10-Q", "2025-05-01", "2025-03-31"),
                                        meta("q0", "10-Q", "2024-11-01", "2024-09-30")], "2025-06-01"))


class PercentileTests(unittest.TestCase):
    def test_lowest_twenty_percent_within_form_are_big_changers(self):
        records = [{"form": "10-K", "similarity": 0.5 + i / 100.0} for i in range(20)]
        records += [{"form": "10-Q", "similarity": 0.1}]      # 另一类只有 1 家：不判大改动者
        ts.add_percentiles(records)
        big = [r for r in records if r["form"] == "10-K" and r["big_changer"]]
        self.assertEqual(len(big), 4)
        self.assertEqual(max(r["similarity"] for r in big), 0.53)
        self.assertFalse(records[-1]["big_changer"])
        self.assertAlmostEqual(records[0]["percentile"], 1 / 20)

    def test_stratified_sample_is_reproducible_and_covers_every_cap_band(self):
        entries = [{"symbol": "S%04d" % i, "market_cap_usd": 3e8 + i * 3.5e6} for i in range(1300)]
        first = ts.stratified_sample(entries, 300)
        self.assertEqual(first, ts.stratified_sample(entries, 300))
        self.assertTrue(280 <= len(first) <= 320)
        bands = {sum(1 for e in first if lo <= e["market_cap_usd"] < hi) for lo, hi in ((3e8, 5e8), (5e8, 1e9), (1e9, 2e9), (2e9, 5e9))}
        self.assertNotIn(0, bands)


if __name__ == "__main__":
    unittest.main()
