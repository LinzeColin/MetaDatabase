"""商业机会覆盖率审计工具：只读研究层产物，照实报 PASS 数与离门槛的差距；不重算任何分数。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from signal_lattice.branches import commercial_audit as A


def verdict(symbol, verdict_, label, score, reasons=(), links=()):
    return {"symbol": symbol, "verdict": verdict_, "label": label, "score": score, "rank_key": score + (1000 if verdict_ == "ABSTAIN" else 0),
            "reasons": list(reasons), "links": [{"url": u} for u in links]}


def doc(with_meta=True):
    meta = {"fundamentals_profile": "commercial",
            "factor_no_evidence": {"base": {"expectations_variant": 1.0, "commercial_value_pool": 0.02}, "risk": {"exposure_gap": 0.1}}}
    return {"verdicts": [verdict("AAA", "ABSTAIN", "WATCHLIST", 58.4, ["DECISION_SCORE_BELOW_DILIGENCE:58.4<65"]),
                         verdict("BBB", "FAILED", "REJECT", 20.0, ["DECISION_SCORE_BELOW_REJECT:20.0<40"]),
                         verdict("CCC", "ABSTAIN", "SCREEN_FLAG", 45.0, ["BASE_COVERAGE_BELOW_FLOOR:0.50<0.60"])],
            "meta": meta if with_meta else {}}


class AuditTests(unittest.TestCase):
    def test_zero_pass_is_reported_as_zero_with_the_gap_to_the_bar(self):
        text = A.render(A.summarize(doc()))
        self.assertIn("PASS 0 只（照实：0 只通过）", text)
        self.assertIn("最高 58.4", text)
        self.assertIn("差 6.6", text)
        self.assertIn("DECISION_SCORE_BELOW_DILIGENCE", text)

    def test_pass_is_listed_with_its_sec_links(self):
        d = doc()
        d["verdicts"].append(verdict("PPP", "PASS", "DILIGENCE_NEXT", 66.0, [], ["https://www.sec.gov/Archives/edgar/data/1/x.htm"]))
        summary = A.summarize(d)
        self.assertEqual(summary["pass"][0]["symbol"], "PPP")
        self.assertIn("https://www.sec.gov/Archives/edgar/data/1/x.htm", A.render(summary))

    def test_old_artifacts_without_factor_table_say_so(self):
        self.assertIn("没有 meta.factor_no_evidence", A.render(A.summarize(doc(with_meta=False))))

    def test_before_after_columns_and_cli(self):
        before = doc()
        before["meta"]["factor_no_evidence"]["base"]["commercial_value_pool"] = 0.2
        with tempfile.TemporaryDirectory() as tmp:
            new, old = Path(tmp) / "new.json", Path(tmp) / "old.json"
            new.write_text(json.dumps(doc()), "utf-8")
            old.write_text(json.dumps(before), "utf-8")
            self.assertEqual(A.main([str(new), "--before", str(old)]), 0)
        text = A.render(A.summarize(doc()), A.summarize(before))
        self.assertIn("(修改前 20.0%)", text)


if __name__ == "__main__":
    unittest.main()
