"""商业机会分支：base_score / risk_deduction / evidence_confidence / E0–E5 / decision_score 公式与门禁；
NO_EVIDENCE 不是中值也不是 0；E 级别不得越级（推算的财报日不是已确认催化剂）；PASS 必带 SEC 原文链接；时点正确。"""

from __future__ import annotations

import dataclasses
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import branch_fixtures as fx
from signal_lattice.branches import commercial as C
from signal_lattice.branches.fundamentals import M, PeerContext, compute_fundamentals
from signal_lattice.branches.scoring_support import NO_EVIDENCE, FactorResult

AS_OF = "2026-09-15"
P = C.DEFAULT_PARAMS


def signals(**kw):
    base = {"public_source_families": 0, "company_filings": 0, "quantified_exposure_metrics": 0,
            "commercial_capture_signals": 0, "current_valuation_observations": 0, "confirmed_catalysts": 0,
            "thesis_falsifiers": 0, "liquidity_checks": 0}
    base.update(kw)
    return base


class PinnedContractTests(unittest.TestCase):
    def test_weights_and_thresholds_are_the_documented_ones(self):
        self.assertEqual(list(P["base_weights"].values()), [12, 16, 12, 10, 12, 10, 10, 7, 5, 6])
        self.assertEqual(sum(P["base_weights"].values()), 100)
        self.assertEqual(list(P["risk_max_deductions"].values()), [8, 7, 6, 5, 4, 4, 3, 3])
        self.assertEqual(sum(P["risk_max_deductions"].values()), 40)
        self.assertEqual(list(P["confidence_weights"].values()), [20, 20, 20, 15, 10, 10, 5])
        d = P["decision"]
        self.assertEqual((d["uncertainty_coefficient"], d["reject_below"], d["screen_flag_below"], d["watchlist_below"],
                          d["diligence_min_confidence"], d["advance_min_score"], d["advance_min_confidence"]),
                         (0.15, 40, 55, 65, 55, 75, 65))

    def test_params_file_in_stock_skill_equals_builtin_defaults(self):
        loaded, findings = C.load_commercial_params()
        self.assertEqual((loaded, findings), (C.DEFAULT_PARAMS, []))
        self.assertEqual(C.DEFAULT_PARAMS_PATH.parts[-3:], ("stock-commercial-opportunities-skill", "runtime", "params.json"))

    def test_broken_params_fall_back_with_a_finding(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, mutate in {
                "weights": lambda p: p["base_weights"].update(commercial_value_pool=13),
                "risk_sum": lambda p: p["risk_max_deductions"].update(exposure_gap=9),
                "confidence": lambda p: p["confidence_weights"].pop("recency"),
                "thresholds": lambda p: p["decision"].update(reject_below=70),
                "extra": lambda p: p.update(other=1),
            }.items():
                params = json.loads(json.dumps(C.DEFAULT_PARAMS))
                mutate(params)
                path = Path(tmp) / (name + ".json")
                path.write_text(json.dumps(params), "utf-8")
                loaded, findings = C.load_commercial_params(path)
                self.assertEqual(loaded, C.DEFAULT_PARAMS, name)
                self.assertEqual([f["code"] for f in findings], ["PARAMS_INVALID"], name)
            loaded, findings = C.load_commercial_params(Path(tmp) / "absent.json")
            self.assertEqual(findings[0]["code"], "PARAMS_FILE_MISSING")


class MaturityGateTests(unittest.TestCase):
    def test_each_level_needs_its_signals_and_gaps_take_the_lower_level(self):
        e = C.evidence_maturity
        self.assertEqual(e(signals()), "E0")
        self.assertEqual(e(signals(public_source_families=3)), "E1")
        self.assertEqual(e(signals(company_filings=1, quantified_exposure_metrics=1)), "E2")
        self.assertEqual(e(signals(company_filings=1, quantified_exposure_metrics=1, commercial_capture_signals=1)), "E3")
        e3plus = dict(company_filings=1, quantified_exposure_metrics=1, commercial_capture_signals=1,
                      current_valuation_observations=1)
        self.assertEqual(e(signals(**e3plus)), "E3")                                   # 有估值没有已确认催化剂：仍是 E3
        self.assertEqual(e(signals(**e3plus, confirmed_catalysts=1)), "E4")
        self.assertEqual(e(signals(**e3plus, confirmed_catalysts=1, thesis_falsifiers=2, liquidity_checks=1)), "E5")
        self.assertEqual(e(signals(**e3plus, confirmed_catalysts=1, thesis_falsifiers=1, liquidity_checks=1)), "E4")

    def test_status_gates(self):
        d = P["decision"]
        s = C.decision_status
        self.assertEqual(s(39.9, 90, "E4", [], True, d), "REJECT")
        self.assertEqual(s(80, 90, "E4", ["x"], True, d), "REJECT")
        self.assertEqual(s(50, 90, "E4", [], True, d), "SCREEN_FLAG")
        self.assertEqual(s(80, 90, "E1", [], True, d), "SCREEN_FLAG")
        self.assertEqual(s(80, 90, "E4", [], False, d), "SCREEN_FLAG")                 # 无敞口归因不高于 SCREEN_FLAG
        self.assertEqual(s(60, 90, "E3", [], True, d), "WATCHLIST")
        self.assertEqual(s(70, 54.9, "E3", [], True, d), "WATCHLIST")
        self.assertEqual(s(70, 60, "E3", [], True, d), "DILIGENCE_NEXT")
        self.assertEqual(s(80, 90, "E3", [], True, d), "DILIGENCE_NEXT")                # 无 E4 不得 ADVANCE_RESEARCH
        self.assertEqual(s(80, 64.9, "E4", [], True, d), "DILIGENCE_NEXT")
        self.assertEqual(s(75, 65, "E4", [], True, d), "ADVANCE_RESEARCH")

    def test_verdict_mapping(self):
        self.assertEqual(C.STATUS_TO_VERDICT, {"ADVANCE_RESEARCH": "PASS", "DILIGENCE_NEXT": "PASS", "WATCHLIST": "ABSTAIN",
                                               "SCREEN_FLAG": "ABSTAIN", "REJECT": "FAILED"})


def factors(**ratings):
    out = {}
    for name in C.BASE_DIMENSIONS:
        r = ratings.get(name, 8.0)
        out[name] = FactorResult(name, r, "t") if r is not None else FactorResult(name, None, "no", (), "NO_EVIDENCE")
    return out


def risks(**ratings):
    out = {}
    for name in C.RISK_FACTORS:
        r = ratings.get(name, 2.0)
        out[name] = FactorResult(name, r, "t") if r is not None else FactorResult(name, None, "no", (), "NO_EVIDENCE")
    return out


class FormulaTests(unittest.TestCase):
    CONF = {k: 8.0 for k in C.CONFIDENCE_FACTORS}

    def test_decision_score_formula(self):
        base = factors()                      # 全 8 分
        risk = risks(exposure_gap=5.0)        # 其余 2
        r = C.compose(base, risk, self.CONF, P, "E3")
        self.assertAlmostEqual(r["base_score"], 80.0)
        expected_risk = sum((5.0 if k == "exposure_gap" else 2.0) / 10 * m for k, m in P["risk_max_deductions"].items())
        self.assertAlmostEqual(r["risk_deduction"], expected_risk)
        self.assertAlmostEqual(r["evidence_confidence"], 80.0)
        self.assertAlmostEqual(r["uncertainty_penalty"], 0.15 * 20)
        self.assertAlmostEqual(r["decision_score"], 80.0 - expected_risk - 3.0)

    def test_no_evidence_dimension_is_excluded_not_zero_not_midpoint(self):
        with_gap = C.compose(factors(expectations_variant=None), risks(), self.CONF, P, "E3")
        # 有证据的 9 个维度都是 8 分：归一后仍是 80，而不是被 0 分拉低到 70.4，也不是被中值 5 分拉到 ~76
        self.assertAlmostEqual(with_gap["base_score"], 80.0)
        self.assertAlmostEqual(with_gap["coverage"], 0.88)
        self.assertTrue(with_gap["verifiable"])

    def test_unobserved_risk_deducts_nothing(self):
        a = C.compose(factors(), risks(expectations_priced_in=None), self.CONF, P, "E3")
        b = C.compose(factors(), risks(expectations_priced_in=0.0), self.CONF, P, "E3")
        self.assertAlmostEqual(a["risk_deduction"], b["risk_deduction"])

    def test_coverage_floor_and_required_dimensions_block_a_pass(self):
        strong = C.compose(factors(), risks(), {k: 10.0 for k in C.CONFIDENCE_FACTORS}, P, "E3")
        self.assertEqual(strong["status"], "DILIGENCE_NEXT")
        no_exposure = C.compose(factors(issuer_exposure_attribution=None), risks(), self.CONF, P, "E3")
        self.assertFalse(no_exposure["verifiable"])
        self.assertEqual(no_exposure["status"], "SCREEN_FLAG")
        thin = C.compose(factors(commercial_value_pool=None, beneficiary_position=None, expectations_variant=None,
                                 valuation_support=None), risks(), {k: 10.0 for k in C.CONFIDENCE_FACTORS}, P, "E3")
        self.assertLess(thin["coverage"], 0.6)
        self.assertEqual(thin["status"], "WATCHLIST")   # 覆盖不足：不给 DILIGENCE_NEXT

    def test_confidence_override_and_clamping(self):
        r = C.compose(factors(), risks(), self.CONF, P, "E3", confidence_override=-50)
        self.assertEqual(r["evidence_confidence"], 0.0)
        self.assertAlmostEqual(r["uncertainty_penalty"], 15.0)


def peer_context(store, market, as_of):
    """同 SIC 的 9 家合成同业：增速与毛利率都更低、估值更贵。"""
    me = compute_fundamentals(store, market, as_of)
    members = [me]
    for i in range(9):
        members.append(dataclasses.replace(
            me, cik=9000 + i, symbol="P%d" % i,
            revenue_yoy=M(0.10 + 0.02 * i), gross_margin=M(0.28 + 0.02 * i),
            cap_sales=M(2.5 + 0.3 * i), cap_gp=M(6.0 + 0.5 * i)))
    return me, PeerContext.build(members)


class ScoredCompanyTests(unittest.TestCase):
    def setUp(self):
        self.store = fx.build_store()
        self.fund, self.peers = peer_context(self.store, fx.market(), AS_OF)
        self.receipt = C.score_commercial(self.store, fx.market(), AS_OF, C.DEFAULT_PARAMS, [], self.peers, self.fund)
        self.d = self.receipt.detail

    def test_estimated_catalyst_never_counts_as_confirmed_so_e_level_stops_at_e3(self):
        self.assertEqual(self.d["evidence_signals"]["confirmed_catalysts"], 0)
        self.assertEqual(self.d["maturity_code"], "E3")
        self.assertNotEqual(self.d["status"], "ADVANCE_RESEARCH")
        self.assertIn("MATURITY_E3_BELOW_E4:NO_CONFIRMED_CATALYST(ESTIMATED_ONLY)", self.receipt.reasons)
        cat = self.d["base_dimensions"]["catalyst_revision_path"]
        self.assertEqual(cat["status"], "ESTIMATED")
        self.assertIn("ESTIMATED", cat["basis"])

    def test_exposure_falls_back_to_revenue_and_rpo_and_says_so(self):
        exp = self.d["base_dimensions"]["issuer_exposure_attribution"]
        self.assertIn("REVENUE_LEVEL_ONLY", exp["basis"])
        self.assertIn("RPO", exp["basis"])
        self.assertLessEqual(exp["rating"], 6)
        self.assertEqual(self.d["evidence_signals"]["quantified_exposure_metrics"], 2)   # 营收同比 + RPO

    def test_unobservable_dimensions_are_reported_as_no_evidence(self):
        self.assertEqual(self.d["base_dimensions"]["expectations_variant"]["rating"], NO_EVIDENCE)
        self.assertGreaterEqual(self.d["no_evidence_ratio"]["base"], 1)
        alone = C.score_commercial(self.store, fx.market(), AS_OF, C.DEFAULT_PARAMS, [], None)
        self.assertEqual(alone.detail["base_dimensions"]["commercial_value_pool"]["rating"], NO_EVIDENCE)  # 没有同业样本
        self.assertEqual(alone.detail["base_dimensions"]["beneficiary_position"]["rating"], NO_EVIDENCE)

    def test_pass_carries_primary_sec_links(self):
        self.assertEqual(self.receipt.verdict, "PASS", (self.receipt.reasons, self.d["decision_score"]))
        self.assertEqual(self.receipt.label, "DILIGENCE_NEXT")
        self.assertTrue(self.d["primary_links"])
        for link in self.d["primary_links"]:
            self.assertRegex(link["url"], r"^https://www\.sec\.gov/Archives/edgar/data/1234567/")

    def test_pass_without_link_is_downgraded(self):
        with mock.patch.object(C, "_primary_links", return_value=[]):
            r = C.score_commercial(self.store, fx.market(), AS_OF, C.DEFAULT_PARAMS, [], self.peers, self.fund)
        self.assertEqual(r.verdict, "ABSTAIN")
        self.assertEqual(r.reasons[0], "PASS_REQUIRES_PRIMARY_SEC_LINK")

    def test_sensitivity_recomputes_the_three_skill_shocks(self):
        sens = self.d["sensitivity"]
        for key in ("baseline", "exposure_minus_2", "priced_in_risk_plus_2", "confidence_minus_20", "flips"):
            self.assertIn(key, sens)
        self.assertLessEqual(sens["confidence_minus_20"]["decision_score"], self.d["decision_score"])

    def test_falsifiers_are_written_at_publish_time(self):
        self.assertGreaterEqual(len(self.d["falsifiers"]), 3)
        self.assertGreaterEqual(self.d["evidence_signals"]["thesis_falsifiers"], 2)

    def test_immaterial_rpo_is_ignored_as_order_evidence(self):
        facts = fx.strong_company_facts()
        facts["facts"]["us-gaap"]["RevenueRemainingPerformanceObligation"] = fx._instant(
            "x", {"2025-06-30": 1e6, "2025-12-31": 1.5e6, "2026-06-30": 2e6})[1]
        store = fx.build_store(facts)
        r = C.score_commercial(store, fx.market(), AS_OF, C.DEFAULT_PARAMS, [], None)
        self.assertNotIn("RPO 同比", r.detail["base_dimensions"]["financial_capture_path"]["basis"])
        self.assertNotIn("有实质 RPO", r.detail["base_dimensions"]["issuer_exposure_attribution"]["basis"])
        self.assertEqual(r.detail["evidence_signals"]["quantified_exposure_metrics"], 1)   # 只剩营收同比

    def test_weak_company_is_rejected_or_flagged_not_passed(self):
        weak = C.score_commercial(fx.build_store(fx.weak_company_facts()), fx.market(cap=2e8, dollar_volume=5e6), AS_OF,
                                  C.DEFAULT_PARAMS, [], None)
        self.assertNotEqual(weak.verdict, "PASS")


class PointInTimeTests(unittest.TestCase):
    FUTURE = ("0001234567-26-000021",)

    def score(self, store, as_of):
        return C.score_commercial(store, fx.market(as_of=as_of), as_of, C.DEFAULT_PARAMS, [], None)

    def test_filings_after_as_of_do_not_change_the_earlier_score(self):
        as_of = "2026-07-15"
        a = self.score(fx.build_store(), as_of)
        b = self.score(fx.build_store(drop_accessions=self.FUTURE), as_of)
        self.assertEqual(a.to_dict(), b.to_dict())
        for group in ("base_dimensions", "risk_factors"):
            for fr in a.detail[group].values():
                for ref in fr["refs"]:
                    if ref.get("filed"):
                        self.assertLessEqual(ref["filed"], as_of)

    def test_score_changes_once_the_filing_is_visible(self):
        store = fx.build_store()
        before, after = self.score(store, "2026-07-15"), self.score(store, "2026-09-15")
        self.assertNotEqual(before.detail["base_dimensions"], after.detail["base_dimensions"])

    def test_mismatched_fundamentals_are_rejected(self):
        store = fx.build_store()
        f = compute_fundamentals(store, fx.market(as_of="2026-07-15"), "2026-07-15")
        with self.assertRaises(ValueError):
            C.score_commercial(store, fx.market(), "2026-09-15", C.DEFAULT_PARAMS, [], None, fundamentals=f)


if __name__ == "__main__":
    unittest.main()
