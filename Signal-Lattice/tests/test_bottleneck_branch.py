"""瓶颈分支：严格按 scoring_model.md 的五维、几何平均、门、持续期乘数；NO_EVIDENCE 不是中值也不是 0；
时点正确；PASS 必带 SEC 原文链接；关键词只是标记。"""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import branch_fixtures as fx
from signal_lattice.branches import bottleneck as B
from signal_lattice.branches.fundamentals import compute_fundamentals
from signal_lattice.branches.scoring_support import NO_EVIDENCE
from signal_lattice.branches.textmarkers import MARKER_MIN_COUNT, TextMarkers

AS_OF = "2026-09-15"


def markers(filed="2026-03-02", accession="0001234567-26-000004", counts=None):
    counts = counts or {"sole_source": 3, "capacity_constrained": 2, "lead_times": 4, "backlog": 5, "allocation": 0}
    return TextMarkers(fx.CIK, accession, "10-K", filed, "2025-12-31",
                       "https://www.sec.gov/Archives/edgar/data/%d/%s/doc0004.htm" % (fx.CIK, accession.replace("-", "")),
                       10000, counts, {})


class ScoringModelPinnedTests(unittest.TestCase):
    """默认参数必须原样等于 scoring_model.md 里的权重与门。"""

    def test_weights_and_gates_are_the_documented_ones(self):
        w = B.DEFAULT_PARAMS["dimension_weights"]
        self.assertEqual(list(w["constraint"].values()), [15, 15, 10, 10, 15, 15, 10, 10])
        self.assertEqual(list(w["capture"].values()), [15, 15, 15, 10, 10, 10, 10, 10, 5])
        self.assertEqual(list(w["mispricing"].values()), [20, 20, 10, 15, 15, 10, 10])
        self.assertEqual(list(w["evidence"].values()), [25, 20, 15, 15, 15, 10])
        self.assertEqual(list(w["investability"].values()), [15, 15, 15, 10, 10, 15, 10, 10])
        for dim in w.values():
            self.assertEqual(sum(dim.values()), 100)
        g = B.DEFAULT_PARAMS["gates"]
        self.assertEqual((g["constraint_min"], g["capture_min"], g["evidence_min"], g["investability_min"],
                          g["mispricing_min"], g["candidate_min_final"], g["priority_min_final"]),
                         (60, 55, 60, 50, 45, 62, 75))
        d = B.DEFAULT_PARAMS["duration"]
        self.assertEqual((d["upper_bounds_months"], d["multipliers"]), ([0, 6, 12, 24, 48], [0.50, 0.70, 0.85, 1.00, 1.07, 1.10]))

    def test_every_factor_documents_its_source(self):
        for dim, factors in B.DEFAULT_PARAMS["dimension_weights"].items():
            for name in factors:
                self.assertIn(name, B.FACTOR_SOURCES, name)

    def test_params_file_in_stock_skill_equals_builtin_defaults(self):
        loaded, findings = B.load_bottleneck_params()
        self.assertEqual(findings, [])
        self.assertEqual(loaded, B.DEFAULT_PARAMS)
        self.assertTrue(B.DEFAULT_PARAMS_PATH.is_file())
        self.assertEqual(B.DEFAULT_PARAMS_PATH.parts[-3:], ("bottleneck-serenity-skill", "runtime", "params.json"))


class ParamsValidationTests(unittest.TestCase):
    def write(self, tmp, mutate):
        params = json.loads(json.dumps(B.DEFAULT_PARAMS))
        mutate(params)
        path = Path(tmp) / "params.json"
        path.write_text(json.dumps(params), "utf-8")
        return path

    def test_broken_files_fall_back_to_defaults_and_record_a_finding(self):
        with tempfile.TemporaryDirectory() as tmp:
            cases = {
                "weights": lambda p: p["dimension_weights"]["constraint"].update(funded_demand=16),
                "missing_key": lambda p: p["gates"].pop("mispricing_min"),
                "extra_key": lambda p: p.update(surprise=1),
                "bad_table": lambda p: p["tables"]["liquidity_dollar_volume"].update(direction="sideways"),
                "coverage_range": lambda p: p["coverage"]["min_by_dimension"].update(constraint=1.5),
                "unknown_required": lambda p: p["coverage"]["required_factors"].update(constraint=["nope"]),
                "non_monotone": lambda p: p["tables"]["funded_demand_rpo_yoy"].update(cuts=[[0.6, 1], [0.3, 4]]),
            }
            for name, mutate in cases.items():
                path = self.write(tmp, mutate)
                params, findings = B.load_bottleneck_params(path)
                self.assertEqual(params, B.DEFAULT_PARAMS, name)
                self.assertEqual([f["code"] for f in findings], ["PARAMS_INVALID"], name)

    def test_missing_and_unparseable_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            params, findings = B.load_bottleneck_params(Path(tmp) / "absent.json")
            self.assertEqual((params, findings[0]["code"]), (B.DEFAULT_PARAMS, "PARAMS_FILE_MISSING"))
            bad = Path(tmp) / "bad.json"
            bad.write_text("{not json", "utf-8")
            params, findings = B.load_bottleneck_params(bad)
            self.assertEqual((params, findings[0]["code"]), (B.DEFAULT_PARAMS, "PARAMS_INVALID"))

    def test_finding_is_carried_into_the_receipt(self):
        store = fx.build_store()
        findings = [{"code": "PARAMS_FILE_MISSING", "detail": "x", "action": "USING_BUILTIN_DEFAULTS"}]
        r = B.score_bottleneck(store, fx.market(), AS_OF, B.DEFAULT_PARAMS, findings, None, markers())
        self.assertIn("PARAMS_FINDING:PARAMS_FILE_MISSING", r.reasons)
        self.assertEqual(r.detail["params_findings"], findings)


class FundamentalsTests(unittest.TestCase):
    def test_ttm_and_yoy_come_from_annual_plus_ytd_minus_prior_ytd(self):
        f = compute_fundamentals(fx.build_store(), fx.market(), AS_OF)
        self.assertEqual(f.revenue_ttm.value, 600e6 + 420e6 - 280e6)
        self.assertEqual(f.revenue_ttm_prior.value, 400e6 + 280e6 - 180e6)
        self.assertAlmostEqual(f.revenue_yoy.value, 740 / 500 - 1)
        self.assertAlmostEqual(f.gross_margin.value, 375 / 740)
        self.assertGreater(f.gm_change_bps.value, 700)
        self.assertAlmostEqual(f.rpo_yoy.value, 640 / 300 - 1)
        self.assertAlmostEqual(f.rpo_months.value, 640e6 / (740e6 / 12))
        self.assertAlmostEqual(f.share_change_yoy.value, 49 / 50.5 - 1)
        self.assertEqual(f.net_cash.value, 330e6 - 30e6)

    def test_every_metric_carries_an_sec_link(self):
        f = compute_fundamentals(fx.build_store(), fx.market(), AS_OF)
        for metric in (f.revenue_ttm, f.gm_change_bps, f.rpo_yoy, f.op_margin, f.net_cash, f.fcf_ttm):
            self.assertTrue(metric.refs)
            for ref in metric.refs:
                self.assertTrue(ref.is_primary_link, ref)
                self.assertRegex(ref.url, r"^https://www\.sec\.gov/Archives/edgar/data/1234567/\d{18}/")

    def test_missing_concepts_are_none_not_zero(self):
        f = compute_fundamentals(fx.build_store(fx.weak_company_facts()), fx.market(), AS_OF)
        for metric in (f.rpo, f.rpo_yoy, f.rpo_months, f.buyback_ttm, f.net_buyback_yield):
            self.assertIsNone(metric.value)
        self.assertTrue(f.debt_assumed_zero)      # 债务标签从未出现：估算而非「拿到了 0」，评分里封顶并标 PROXY
        self.assertEqual(f.debt.note, "DEBT_TAG_ABSENT_ASSUMED_ZERO")

    def test_next_report_is_an_estimate_from_filing_cadence(self):
        f = compute_fundamentals(fx.build_store(), fx.market(), AS_OF)
        est = f.next_report
        self.assertEqual(est.status, "ESTIMATED")
        self.assertEqual(est.est_date, "2026-11-04")  # 2026-09-30 + 35 天滞后中位数
        self.assertEqual(est.days_until, 50)
        self.assertTrue(est.refs)


class StrongCompanyTests(unittest.TestCase):
    def setUp(self):
        self.store = fx.build_store()
        self.receipt = B.score_bottleneck(self.store, fx.market(), AS_OF, B.DEFAULT_PARAMS, [], None, markers())
        self.d = self.receipt.detail

    def test_passes_all_gates_and_carries_primary_links(self):
        self.assertEqual((self.receipt.verdict, self.receipt.label), ("PASS", "CANDIDATE"), self.receipt.reasons)
        self.assertTrue(self.d["primary_links"])
        for link in self.d["primary_links"]:
            self.assertRegex(link["url"], r"^https://www\.sec\.gov/Archives/edgar/data/1234567/")
            self.assertTrue(link["accession"])
        gates = self.d["gates"]
        self.assertEqual([gates[k]["status"] for k in ("A_constraint_reality", "B_scarcity_duration", "C_rent_capture", "D_mispricing")],
                         ["PASS"] * 4)

    def test_final_score_is_core_times_duration_times_neutral_asymmetry(self):
        scores = [self.d["dimensions"][dim]["score"] for dim in B.DIMENSIONS]
        core = math.exp(sum(math.log(max(s, 0.01)) for s in scores) / 5)
        self.assertAlmostEqual(self.d["core_quality"], core, delta=0.02)
        self.assertEqual(self.d["duration"]["status"], "LOWER_BOUND_FROM_BACKLOG")
        runway = 640e6 / (740e6 / 12) - 3
        self.assertAlmostEqual(self.d["duration"]["monetizable_runway_months_lower_bound"], runway, places=1)
        self.assertEqual(self.d["duration"]["band_multiplier"], 0.85)  # 6-12 个月档
        self.assertEqual(self.d["duration"]["multiplier"], 0.85)
        self.assertEqual(self.d["scenario_asymmetry"], {"status": NO_EVIDENCE, "multiplier": 1.0})
        self.assertAlmostEqual(self.d["final_score"], self.d["core_quality"] * 0.85, delta=0.02)
        self.assertGreaterEqual(self.d["final_score"], 62)
        self.assertLess(self.d["final_score"], 75)  # 没有情景不对称，RESEARCH_PRIORITY 不可达

    def test_no_evidence_factors_are_excluded_not_zero_and_not_midpoint(self):
        con = self.d["factors"]["constraint"]
        for name in ("architectural_necessity", "qualification_barrier", "substitution_difficulty", "policy_resilience"):
            self.assertEqual(con[name]["rating"], NO_EVIDENCE)
            self.assertEqual(con[name]["status"], "NO_EVIDENCE")
        dim = self.d["dimensions"]["constraint"]
        self.assertIn("architectural_necessity", dim["no_evidence_factors"])
        weights = B.DEFAULT_PARAMS["dimension_weights"]["constraint"]
        observed = [n for n in weights if con[n]["rating"] != NO_EVIDENCE]
        expected = sum(con[n]["rating"] / 5 * weights[n] for n in observed) / sum(weights[n] for n in observed) * 100
        self.assertAlmostEqual(dim["score"], expected, places=1)
        self.assertAlmostEqual(dim["coverage"], sum(weights[n] for n in observed) / 100, places=3)

    def test_each_observed_factor_documents_basis_and_is_traceable(self):
        for dim, factors in self.d["factors"].items():
            for name, fr in factors.items():
                self.assertTrue(fr["basis"], (dim, name))
                if fr["rating"] != NO_EVIDENCE and fr["status"] == "OBSERVED" and dim in ("constraint", "capture") and name not in (
                        "supplier_concentration", "expansion_lead_time"):
                    self.assertTrue(fr["refs"], (dim, name))

    def test_all_five_dimensions_and_four_gates_are_reported(self):
        self.assertEqual(set(self.d["dimensions"]), set(B.DIMENSIONS))
        self.assertEqual(set(self.d["gates"]) >= {"A_constraint_reality", "B_scarcity_duration", "C_rent_capture", "D_mispricing"}, True)

    def test_hard_flags_are_machine_readable(self):
        flags = self.d["hard_flags"]
        self.assertIs(flags["no_primary_evidence"], False)
        self.assertIs(flags["no_material_revenue_bridge"], False)
        self.assertIs(flags["unfunded_financing_gap"], False)
        self.assertEqual(flags["wrong_entity_or_ticker"], "NOT_EVALUATED")
        self.assertTrue(self.d["equity_bridge"]["complete"])


class KeywordMarkersTests(unittest.TestCase):
    """关键词只作证据标记：不得推高收益相关维度（捕获、错误定价）。"""

    def setUp(self):
        self.store = fx.build_store()

    def score(self, text):
        return B.score_bottleneck(self.store, fx.market(), AS_OF, B.DEFAULT_PARAMS, [], None, text)

    def test_markers_do_not_change_capture_or_mispricing(self):
        without = self.score(None).detail
        heavy = self.score(markers(counts={g: 50 for g in ("sole_source", "capacity_constrained", "lead_times", "backlog", "allocation")})).detail
        for dim in ("capture", "mispricing", "investability"):
            self.assertEqual(without["dimensions"][dim], heavy["dimensions"][dim], dim)
            self.assertEqual(without["factors"][dim], heavy["factors"][dim], dim)

    def test_markers_alone_cannot_pass_the_constraint_gate(self):
        store = fx.build_store(fx.weak_company_facts())
        heavy = markers(counts={g: 50 for g in ("sole_source", "capacity_constrained", "lead_times", "backlog", "allocation")})
        r = B.score_bottleneck(store, fx.market(), AS_OF, B.DEFAULT_PARAMS, [], None, heavy)
        con = r.detail["factors"]["constraint"]
        for name in ("supplier_concentration", "expansion_lead_time"):
            self.assertLessEqual(con[name]["rating"], B.DEFAULT_PARAMS["text_markers"]["marker_cap_rating"])
        self.assertLessEqual(con["current_tightness"]["rating"], B.DEFAULT_PARAMS["text_markers"]["marker_cap_rating"] + 0)
        self.assertNotEqual(r.verdict, "PASS")

    def test_single_mention_is_not_a_marker(self):
        self.assertEqual(MARKER_MIN_COUNT, 2)
        r = self.score(markers(counts={"sole_source": 1, "capacity_constrained": 1, "lead_times": 1, "backlog": 1, "allocation": 1}))
        con = r.detail["factors"]["constraint"]
        self.assertEqual(con["supplier_concentration"]["rating"], 1)
        self.assertEqual(con["expansion_lead_time"]["rating"], 1)
        self.assertEqual(con["supplier_concentration"]["refs"], [])

    def test_unscanned_text_is_no_evidence_and_makes_constraint_unverifiable(self):
        r = self.score(None)
        con = r.detail["factors"]["constraint"]
        self.assertEqual(con["supplier_concentration"]["rating"], NO_EVIDENCE)
        self.assertEqual(con["expansion_lead_time"]["rating"], NO_EVIDENCE)
        dim = r.detail["dimensions"]["constraint"]
        self.assertFalse(dim["verifiable"])
        self.assertTrue(dim["reason"].startswith("COVERAGE_BELOW_FLOOR"))
        self.assertEqual(r.verdict, "ABSTAIN")
        self.assertIn("DIMENSION_UNVERIFIABLE:constraint:" + dim["reason"], r.reasons)

    def test_marker_links_count_toward_primary_evidence_but_only_as_refs(self):
        r = self.score(markers())
        text_links = [l for l in r.detail["primary_links"] if "doc0004" in l["url"]]
        self.assertTrue(text_links or r.detail["text_markers"])
        self.assertEqual(r.detail["text_markers"]["accession"], "0001234567-26-000004")


class GateAndVerdictTests(unittest.TestCase):
    def test_financing_gap_is_a_fatal_flag(self):
        store = fx.build_store(fx.weak_company_facts())
        r = B.score_bottleneck(store, fx.market(cap=2e8, dollar_volume=5e6), AS_OF, B.DEFAULT_PARAMS, [], None, markers())
        self.assertEqual((r.verdict, r.label), ("FAILED", "AVOID"))
        self.assertEqual(r.reasons, ["HARD_FLAG:unfunded_financing_gap"])
        self.assertIs(r.detail["hard_flags"]["unfunded_financing_gap"], True)

    def test_weak_capture_is_bottleneck_not_equity(self):
        facts = fx.weak_company_facts()
        us = facts["facts"]["us-gaap"]
        us["NetCashProvidedByUsedInOperatingActivities"] = fx._flow(
            "x", {"FY24": 5e6, "H124": 2e6, "FY25": 5e6, "H125": 2e6, "H126": 1e6})[1]   # 现金流为正，不触发融资缺口
        us["CashAndCashEquivalentsAtCarryingValue"] = fx._instant(
            "x", {"2025-06-30": 900e6, "2025-12-31": 900e6, "2026-06-30": 900e6})[1]
        r = B.score_bottleneck(fx.build_store(facts), fx.market(), AS_OF, B.DEFAULT_PARAMS, [], None, markers())
        self.assertEqual((r.verdict, r.label), ("FAILED", "BOTTLENECK_NOT_EQUITY"), r.reasons)
        self.assertTrue(r.reasons[0].startswith("GATE_C_CAPTURE_BELOW_MIN"))
        self.assertLess(r.detail["dimensions"]["capture"]["score"], 55)

    def test_no_revenue_is_a_failed_bridge_but_missing_data_only_abstains(self):
        facts = fx.strong_company_facts()
        del facts["facts"]["us-gaap"]["PaymentsToAcquirePropertyPlantAndEquipment"]
        r = B.score_bottleneck(fx.build_store(facts), fx.market(), AS_OF, B.DEFAULT_PARAMS, [], None, markers())
        self.assertEqual(r.verdict, "ABSTAIN")
        self.assertTrue(any(x.startswith("HARD_FLAG:no_material_revenue_bridge:DATA_MISSING") for x in r.reasons))
        self.assertIs(r.detail["hard_flags"]["no_material_revenue_bridge"], True)

    def test_unknown_runway_uses_conservative_multiplier_and_is_reported(self):
        facts = fx.strong_company_facts()
        del facts["facts"]["us-gaap"]["RevenueRemainingPerformanceObligation"]
        r = B.score_bottleneck(fx.build_store(facts), fx.market(), AS_OF, B.DEFAULT_PARAMS, [], None, markers())
        self.assertEqual(r.detail["duration"]["status"], NO_EVIDENCE)
        self.assertEqual(r.detail["duration"]["multiplier"], 0.85)
        self.assertIsNone(r.detail["duration"]["monetizable_runway_months_lower_bound"])
        self.assertEqual(r.detail["gates"]["B_scarcity_duration"]["status"], "UNVERIFIED")
        # 没有 RPO：funded_demand 退到营收同比，最高 3
        self.assertEqual(r.detail["factors"]["constraint"]["funded_demand"]["rating"], 3)

    def test_backlog_is_only_a_lower_bound_it_supports_gate_b_but_never_fails_it(self):
        def with_rpo(latest):
            facts = fx.strong_company_facts()
            facts["facts"]["us-gaap"]["RevenueRemainingPerformanceObligation"] = fx._instant(
                "x", {"2025-06-30": 300e6, "2025-12-31": 420e6, "2026-06-30": latest})[1]
            return B.score_bottleneck(fx.build_store(facts), fx.market(), AS_OF, B.DEFAULT_PARAMS, [], None, markers())

        tiny = with_rpo(5e6)            # 积压只覆盖不到 1 个月营收：下界 <0 个月
        self.assertEqual(tiny.detail["duration"]["band_multiplier"], 0.50)
        self.assertEqual(tiny.detail["duration"]["multiplier"], 0.85)          # 下界不能把乘数压到 0.5，取保守默认
        self.assertEqual(tiny.detail["gates"]["B_scarcity_duration"]["status"], "UNVERIFIED")
        self.assertFalse(any(x.startswith("GATE_B") for x in tiny.reasons))   # 不凭下界阻断
        long_ = with_rpo(1.6e9)         # 积压覆盖约 26 个月：下界 ≥12 个月，合同化斜坡
        self.assertTrue(long_.detail["duration"]["contracted_forward_ramp"])
        self.assertEqual(long_.detail["duration"]["multiplier"], 1.0)
        self.assertEqual(long_.detail["gates"]["B_scarcity_duration"]["status"], "PASS")

    def test_immaterial_rpo_is_not_demand_evidence(self):
        facts = fx.strong_company_facts()
        facts["facts"]["us-gaap"]["RevenueRemainingPerformanceObligation"] = fx._instant(
            "x", {"2025-06-30": 1e6, "2025-12-31": 1.5e6, "2026-06-30": 2e6})[1]   # +100% 但只覆盖约 0.03 个月营收
        r = B.score_bottleneck(fx.build_store(facts), fx.market(), AS_OF, B.DEFAULT_PARAMS, [], None, markers())
        fd = r.detail["factors"]["constraint"]["funded_demand"]
        self.assertEqual(fd["rating"], 3)                              # 退回营收同比的间接证据
        self.assertIn("不作需求证据", fd["basis"])

    def test_missing_debt_tags_are_a_capped_proxy_not_a_free_ride(self):
        with_debt = B.score_bottleneck(fx.build_store(), fx.market(), AS_OF, B.DEFAULT_PARAMS, [], None, markers())
        facts = fx.strong_company_facts()
        del facts["facts"]["us-gaap"]["LongTermDebt"]
        no_tag = B.score_bottleneck(fx.build_store(facts), fx.market(), AS_OF, B.DEFAULT_PARAMS, [], None, markers())
        f = compute_fundamentals(fx.build_store(facts), fx.market(), AS_OF)
        self.assertTrue(f.debt_assumed_zero)
        self.assertEqual(f.net_cash.value, 330e6)
        self.assertEqual(with_debt.detail["factors"]["capture"]["balance_sheet"]["rating"], 5.0)
        bs = no_tag.detail["factors"]["capture"]["balance_sheet"]
        self.assertEqual((bs["rating"], bs["status"]), (3, "PROXY"))
        sv = no_tag.detail["factors"]["investability"]["balance_sheet_survival"]
        self.assertEqual((sv["rating"], sv["status"]), (3, "PROXY"))

    def test_gate_margin_is_the_worst_gate_and_pass_ranks_first(self):
        store = fx.build_store()
        good = B.score_bottleneck(store, fx.market(), AS_OF, B.DEFAULT_PARAMS, [], None, markers())
        unscanned = B.score_bottleneck(store, fx.market(), AS_OF, B.DEFAULT_PARAMS, [], None, None)   # 结构性维度不可核实
        self.assertGreaterEqual(good.detail["gate_margin"], 1.0)
        self.assertEqual(unscanned.detail["gate_margin"], 0.0)        # 有一个门无法核实 → 最差门记 0
        self.assertGreater(good.detail["rank_key"], unscanned.detail["rank_key"])
        self.assertGreater(unscanned.detail["rank_key"], B.rank_key("FAILED", None, 0.99))

    def test_pass_without_a_primary_link_is_downgraded(self):
        store = fx.build_store()
        with mock.patch.object(B, "collect_primary_links", return_value=[]):
            r = B.score_bottleneck(store, fx.market(), AS_OF, B.DEFAULT_PARAMS, [], None, markers())
        self.assertEqual(r.verdict, "ABSTAIN")
        self.assertEqual(r.reasons[0], "PASS_REQUIRES_PRIMARY_SEC_LINK")

    def test_gates_are_not_compensable(self):
        # 其余维度都强，只有可投资性差（成交额贴着下限、登记在中国、近期 NT 迟报）：不能被别的维度补回来。
        late = [("0001234567-26-0000%02d" % i, "NT 10-Q", "2026-05-%02d" % (10 + i), "2026-03-31", "", "") for i in (1, 2)]
        store = fx.build_store(submissions=fx.submissions_payload(extra=late))
        r = B.score_bottleneck(store, fx.market(dollar_volume=3.0e6, state="F4"), AS_OF, B.DEFAULT_PARAMS, [], None, markers())
        inv = r.detail["dimensions"]["investability"]
        self.assertLess(inv["score"], B.DEFAULT_PARAMS["gates"]["investability_min"])
        self.assertGreater(r.detail["dimensions"]["capture"]["score"], 90)
        self.assertGreater(r.detail["dimensions"]["evidence"]["score"], 60)
        self.assertEqual((r.verdict, r.label), ("FAILED", "AVOID"))
        self.assertTrue(r.reasons[0].startswith("INVESTABILITY_BELOW_MIN"))
        self.assertEqual(r.detail["gates"]["investability_min"]["status"], "FAIL")


class PointInTimeTests(unittest.TestCase):
    """时点正确：as_of 之后才申报的数不影响 as_of 当天的打分。"""

    FUTURE = ("0001234567-26-000021",)   # H1'26 10-Q，2026-08-04 申报

    def score(self, store, as_of):
        market = fx.market(as_of=as_of)
        return B.score_bottleneck(store, market, as_of, B.DEFAULT_PARAMS, [], None, markers())

    def test_filings_after_as_of_do_not_change_the_earlier_score(self):
        as_of = "2026-07-15"
        full = fx.build_store()                                   # 库里已经有 2026-08-04 才申报的 10-Q
        without = fx.build_store(drop_accessions=self.FUTURE)     # 库里根本没有这份
        a, b = self.score(full, as_of), self.score(without, as_of)
        self.assertEqual(a.to_dict(), b.to_dict())
        self.assertEqual(a.detail["factors"], b.detail["factors"])
        f = compute_fundamentals(full, fx.market(as_of=as_of), as_of)
        self.assertEqual(f.revenue_ttm.value, 600e6)              # 只见到 FY2025 年报
        for factors in a.detail["factors"].values():
            for fr in factors.values():
                for ref in fr["refs"]:
                    if ref.get("filed"):
                        self.assertLessEqual(ref["filed"], as_of, ref)   # 引用的每一份申报都在 as_of 之前

    def test_the_same_company_scores_differently_once_the_filing_is_visible(self):
        store = fx.build_store()
        before, after = self.score(store, "2026-07-15"), self.score(store, "2026-09-15")
        self.assertNotEqual(before.detail["factors"], after.detail["factors"])
        self.assertIn("2026-06-30", json.dumps(after.detail["factors"]))
        self.assertEqual(compute_fundamentals(store, fx.market(), "2026-09-15").revenue_ttm.value, 740e6)

    def test_restated_values_filed_later_do_not_leak_backwards(self):
        facts = fx.strong_company_facts()
        # FY2025 营收在 2026-08-04 的 10-Q 里被重述为 550（原值 600 于 2026-03-02 申报）
        restated = {"start": "2025-01-01", "end": "2025-12-31", "val": 550e6, "accn": "0001234567-26-000021",
                    "form": "10-Q", "filed": "2026-08-04", "fy": 2025, "fp": "FY"}
        facts["facts"]["us-gaap"]["Revenues"]["units"]["USD"].append(restated)
        store = fx.build_store(facts)
        early = compute_fundamentals(store, fx.market(as_of="2026-07-15"), "2026-07-15")
        late = compute_fundamentals(store, fx.market(), "2026-09-15")
        self.assertEqual(early.revenue_ttm.value, 600e6)          # 原值
        self.assertEqual(late.revenue_ttm.value, 550e6 + 420e6 - 280e6)   # 重述值只在申报日之后可见
        self.assertGreater(late.restatement.value, 0.08)           # 重述被记为潜在矛盾

    def test_score_functions_reject_fundamentals_from_a_different_as_of(self):
        store = fx.build_store()
        f = compute_fundamentals(store, fx.market(as_of="2026-07-15"), "2026-07-15")
        with self.assertRaises(ValueError):
            B.score_bottleneck(store, fx.market(), "2026-09-15", B.DEFAULT_PARAMS, [], None, markers(), fundamentals=f)

    def test_text_markers_filed_after_as_of_are_rejected(self):
        with self.assertRaises(ValueError):
            B.score_bottleneck(fx.build_store(), fx.market(as_of="2026-01-15"), "2026-01-15", B.DEFAULT_PARAMS, [], None,
                               markers(filed="2026-03-02"))


if __name__ == "__main__":
    unittest.main()
