"""缺陷 #13：公司名全大写的转成正常大小写（规则取自 EEI 的 prettyName），页面上不再「喊」。"""

import json
import unittest
from datetime import datetime, timezone

from signal_lattice import hub
from signal_lattice.names import pretty_name
from signal_lattice.research_view import load_research
from hub_fixtures import EVENT, build_view, open_proof, pool_entry, record, run_decision, sec_link, standard_pool, write_research_dir
import tempfile
from pathlib import Path


class PrettyNameRuleTests(unittest.TestCase):
    def test_all_caps_names_become_normal_case_and_keep_the_usual_company_type_spellings(self):
        cases = {
            "KENNAMETAL INC": "Kennametal Inc",
            "NORTHRIM BANCORP INC": "Northrim Bancorp Inc",
            "COMMUNITY FINANCIAL SYSTEM, INC.": "Community Financial System, Inc.",
            "ACME ROBOTICS LLC": "Acme Robotics LLC",
            "ROYAL HOLDING NV": "Royal Holding NV",
            "BANK OF THE WEST PLC": "Bank of the West PLC",
            "AT&T CORP": "AT&T Corp",
            "STATE STREET CORP": "State Street Corp",
            "IBM CREDIT LLC": "IBM Credit LLC",
            "ALPHA AND OMEGA SEMICONDUCTOR LTD": "Alpha and Omega Semiconductor Ltd",
        }
        for raw, expected in cases.items():
            with self.subTest(raw):
                self.assertEqual(pretty_name(raw), expected)

    def test_names_that_are_already_normal_case_or_too_short_are_left_alone(self):
        for raw in ("Howard Hughes Holdings Inc.", "Evolv Technologies Holdings, Inc.", "iShares Russell 2000 ETF", "IBM", "3M", "GE", "", None):
            with self.subTest(raw):
                self.assertEqual(pretty_name(raw), raw)

    def test_the_conversion_is_idempotent(self):
        once = pretty_name("COMMUNITY FINANCIAL SYSTEM, INC.")
        self.assertEqual(pretty_name(once), once)


class NamesReachThePageData(unittest.TestCase):
    def test_a_loaded_research_view_carries_normal_case_names_everywhere(self):
        pool = standard_pool()
        pool[EVENT][0] = record("ALPHA", "PASS", label="POSITIVE_EVENT", score=70.0, name="ALPHA ROBOTICS INC",
                                links=[sec_link("0000000001-26-000001", cik=11, date="2026-09-25")])
        with tempfile.TemporaryDirectory() as tmp:
            root = write_research_dir(Path(tmp), pool)
            # 研究层产物里池子表也是全大写（真实的 SEC 登记名）
            day = next(p for p in Path(root).iterdir() if p.is_dir())
            hubinputs = next(day.glob("hubinputs-*.json"))
            payload = json.loads(hubinputs.read_text("utf-8"))
            for row in payload["pool"]:
                if row["symbol"] == "ALPHA":
                    row["name"] = "ALPHA ROBOTICS INC"
            hubinputs.write_text(json.dumps(payload), "utf-8")
            view = load_research(Path(root))
        self.assertEqual(next(i for i in view.shortlist if i["symbol"] == "ALPHA")["name"], "Alpha Robotics Inc")
        self.assertEqual(view.pool["ALPHA"]["name"], "Alpha Robotics Inc")
        self.assertEqual(view.verdict(EVENT, "ALPHA")["name"], "Alpha Robotics Inc")

    def test_the_decision_and_the_candidate_rows_never_show_an_all_caps_company_name(self):
        pool = standard_pool()
        pool[EVENT][0] = record("ALPHA", "PASS", label="POSITIVE_EVENT", score=70.0, name="ALPHA ROBOTICS INC",
                                links=[sec_link("0000000001-26-000001", cik=11, date="2026-09-25")])
        symbols = {r["symbol"] for rows in pool.values() for r in rows}
        shouting_pool = {s: {**pool_entry(s), "name": s + " ROBOTICS INC"} for s in sorted(symbols)}          # 真实产物里池子表是 SEC 登记的全大写名
        with tempfile.TemporaryDirectory() as tmp:
            view = load_research(write_research_dir(Path(tmp), pool, pool=shouting_pool))
        outcome = run_decision(view, proof=open_proof())
        decision = outcome["decision"]
        self.assertEqual(decision["primary_name"], "Alpha Robotics Inc")
        self.assertIn("Alpha Robotics Inc", decision["rationale"])
        self.assertNotIn("ALPHA ROBOTICS", json.dumps(outcome["candidates"], ensure_ascii=False))
        self.assertNotIn("ALPHA ROBOTICS", json.dumps(decision, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
