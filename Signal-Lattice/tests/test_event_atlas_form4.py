"""Form 4 解析：只认代码 P；10b5-1 计划、卖出、授予、小额都不算机会型买入。"""

from __future__ import annotations

import unittest

from _event_fixtures import form4_xml, txn, wrap_submission

from signal_lattice.evidence.eventstore import EventStore
from signal_lattice.evidence.form4 import Form4ParseError, open_market_purchases, parse_form4
from signal_lattice.evidence.insiders import buys_from_doc, ingest_form4_payload


class ParseTests(unittest.TestCase):
    def test_only_code_p_is_a_purchase(self):
        xml = form4_xml([txn("P", shares=1000, price=25.0), txn("S", shares=500, ad="D"), txn("A", price=0),
                         txn("M", shares=200), txn("F", shares=50, ad="D"), txn("G", shares=10, ad="D")])
        doc = parse_form4(xml)
        self.assertEqual([t.code for t in doc.transactions], ["P", "S", "A", "M", "F", "G"])
        purchases = open_market_purchases(doc)
        self.assertEqual(len(purchases), 1)
        self.assertEqual(purchases[0].amount_usd, 25_000.0)

    def test_sale_code_s_never_counts(self):
        rows = buys_from_doc(parse_form4(form4_xml([txn("S", shares=100000, price=50.0, ad="D")])), "0-26-1", "2026-08-12")
        self.assertEqual(rows, [])

    def test_aff10b5one_flag_marks_plan_trades(self):
        for value, expected in (("true", 1), ("1", 1), ("false", 0), ("0", 0)):
            doc = parse_form4(form4_xml([txn("P")], aff10b5one=value))
            rows = buys_from_doc(doc, "0-26-1", "2026-08-12")
            self.assertEqual(rows[0]["plan_10b5_1"], expected, value)

    def test_footnote_mentioning_rule_10b5_1_marks_plan_trades(self):
        for text in ("Purchase made pursuant to a Rule 10b5-1 trading plan", "under a 10b5‑1 plan adopted in March"):
            doc = parse_form4(form4_xml([txn("P", footnote="F1")], footnotes={"F1": text}))
            self.assertTrue(open_market_purchases(doc)[0].is_10b5_1, text)
        doc = parse_form4(form4_xml([txn("P", footnote="F1")], footnotes={"F1": "Weighted average price."}))
        self.assertFalse(open_market_purchases(doc)[0].is_10b5_1)

    def test_plan_footnote_on_other_line_does_not_taint_plain_purchase(self):
        xml = form4_xml([txn("P", shares=1000, price=20.0), txn("P", shares=2000, price=20.0, footnote="F1")],
                        footnotes={"F1": "made under a Rule 10b5-1 plan"})
        rows = buys_from_doc(parse_form4(xml), "0-26-1", "2026-08-12")
        self.assertEqual(rows[0]["plan_10b5_1"], 0)
        self.assertEqual(rows[0]["amount_usd"], 20_000.0)  # 只合计非计划行

    def test_all_plan_lines_are_kept_but_flagged(self):
        xml = form4_xml([txn("P", footnote="F1")], footnotes={"F1": "Rule 10b5-1 trading plan"})
        rows = buys_from_doc(parse_form4(xml), "0-26-1", "2026-08-12")
        self.assertEqual((len(rows), rows[0]["plan_10b5_1"]), (1, 1))

    def test_missing_price_counts_as_zero_amount(self):
        rows = buys_from_doc(parse_form4(form4_xml([txn("P", shares=100000, price=None)])), "0-26-1", "2026-08-12")
        self.assertEqual(rows[0]["amount_usd"], 0.0)

    def test_joint_filers_each_get_a_row_and_roles_are_read(self):
        xml = form4_xml([txn("P")], owners=((1, "Fund LP", ""), (2, "Smith John", "Chief Financial Officer")))
        rows = buys_from_doc(parse_form4(xml), "0-26-1", "2026-08-12")
        self.assertEqual({r["owner_cik"] for r in rows}, {1, 2})
        self.assertIn("Chief Financial Officer", [r["role"] for r in rows][1])

    def test_full_submission_text_gives_acceptance_time(self):
        doc = parse_form4(wrap_submission(form4_xml([txn("P")]), "20260811093015"))
        self.assertEqual(doc.accepted_at, "2026-08-11T09:30:15Z")
        self.assertEqual(doc.issuer_cik, 1234567)
        self.assertEqual(doc.symbol, "TEST")

    def test_garbage_is_rejected(self):
        with self.assertRaises(Form4ParseError):
            parse_form4("<html>not a form 4</html>")
        with self.assertRaises(Form4ParseError):
            parse_form4("<ownershipDocument><issuer></issuer></ownershipDocument>")

    def test_ingest_stores_buys_and_raw_only_when_p_present(self):
        store = EventStore(":memory:")
        status = ingest_form4_payload(store, wrap_submission(form4_xml([txn("S", ad="D")])).encode(), "A-1", "2026-08-12", "now")
        self.assertEqual((status, store.count("form4_buys"), store.count("form4_raw")), ("OK", 0, 0))
        ingest_form4_payload(store, wrap_submission(form4_xml([txn("P")])).encode(), "A-2", "2026-08-12", "now")
        self.assertEqual((store.count("form4_buys"), store.count("form4_raw"), store.count("insider_p")), (1, 1, 1))
        self.assertEqual(ingest_form4_payload(store, b"junk", "A-3", "2026-08-12", "now"), "PARSE_ERROR")


if __name__ == "__main__":
    unittest.main()
