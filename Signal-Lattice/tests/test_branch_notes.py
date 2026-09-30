"""分支卡片上的一句话说明：取自收据与逐股结论，不按分支写死。"""

import unittest

from signal_lattice import branch_notes


def verdicts(*rows):
    return {"S%02d" % i: {"verdict": verdict, "reasons": list(reasons)} for i, (verdict, reasons) in enumerate(rows)}


class BranchNoteTests(unittest.TestCase):
    def test_an_abstaining_branch_uses_the_receipts_own_reason(self):
        receipt = {"status": "ABSTAIN", "reason": "OOS_BRIER_NOT_BETTER_THAN_BASE_RATE:full_model=0.25309>=const=0.24955", "verdict_counts": {"ABSTAIN": 3}}
        note = branch_notes.describe("equity-foresight-signal", receipt, {}, {})
        self.assertIn("样本外预测力不如常数基准", note)
        self.assertIn("0.253", note)
        self.assertIn("0.250", note)
        self.assertIn("整分支弃权", note)

    def test_an_unknown_receipt_reason_is_passed_through_not_guessed(self):
        note = branch_notes.describe("x", {"status": "ABSTAIN", "reason": "SOMETHING_NEW:42"}, {}, {})
        self.assertIn("SOMETHING_NEW:42", note)

    def test_zero_passes_and_missing_constraint_evidence_names_the_missing_factors_from_the_branch_meta(self):
        meta = {"factor_no_evidence": {"constraint": {"funded_demand": 0.19, "expansion_lead_time": 0.9992, "supplier_concentration": 0.9968,
                                                      "qualification_barrier": 1.0, "current_tightness": 0.5}}}
        note = branch_notes.describe("bottleneck-serenity-skill", {"status": "PASS", "verdict_counts": {"PASS": 0}}, {}, meta)
        self.assertIn("0 家通过", note)
        self.assertIn("扩产交期", note)
        self.assertIn("供应商集中度", note)
        self.assertIn("99%", note)
        self.assertNotIn("有资金支撑的需求", note)                       # 只有 19% 无证据的因子不算

    def test_the_sentence_follows_the_data_when_the_data_changes(self):
        meta = {"factor_no_evidence": {"constraint": {"expansion_lead_time": 0.2, "supplier_concentration": 0.1, "qualification_barrier": 0.3}}}
        rows = verdicts(("FAILED", ["DECISION_SCORE_BELOW_REJECT:39<40", "MATURITY_E2_BELOW_E4:NO_CONFIRMED_CATALYST"]),
                        ("FAILED", ["DECISION_SCORE_BELOW_REJECT:38<40"]), ("ABSTAIN", ["STATUS:SCREEN_FLAG"]))
        note = branch_notes.describe("stock-commercial-opportunities", {"status": "PASS", "verdict_counts": {"PASS": 0}}, rows, meta)
        self.assertIn("0 家通过", note)
        self.assertIn("综合分低于淘汰线，2 家", note)
        self.assertIn("证据成熟度没到 E4", note)
        self.assertNotIn("扩产交期", note)

    def test_a_branch_with_passes_says_how_many_and_why_the_rest_did_not(self):
        rows = verdicts(("PASS", ["有正向事件且近 90 天无增发/ATM/招股"]), ("ABSTAIN", ["近 90 天没有满足门槛的正向事件"]),
                        ("ABSTAIN", ["近 90 天没有满足门槛的正向事件"]), ("FAILED", ["稀释失效条件已触发：424B5：ATM"]))
        note = branch_notes.describe("equity-event-atlas", {"status": "PASS", "verdict_counts": {"PASS": 1}}, rows, {})
        self.assertIn("本轮 1 家通过", note)
        self.assertIn("近 90 天没有满足门槛的正向事件，2 家", note)

    def test_the_environment_branch_says_it_does_not_pick_stocks(self):
        note = branch_notes.describe("global-equity-lead-lag-atlas", {"status": "PASS", "verdict_counts": {}}, {}, {"regime": "NO_CONFIRMED_LEAD_LAG", "note": "只作环境输入"})
        self.assertIn("只作环境输入", note)
        self.assertIn("NO_CONFIRMED_LEAD_LAG", note)


if __name__ == "__main__":
    unittest.main()
