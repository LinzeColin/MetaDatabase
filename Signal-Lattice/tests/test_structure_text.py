"""10-K/10-Q 正文结构性证据抽取：五类抽取、方向判别（瓶颈拥有者 vs 上游依赖风险）、误报排除、缓存；
以及接进瓶颈分支因子后的分数锚点（有数字才能到 3 以上；上游依赖只进风险；判不出方向不计分）。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import branch_fixtures as fx
from signal_lattice.branches import bottleneck as B
from signal_lattice.branches import structure_factors as SF
from signal_lattice.branches.scoring_support import NO_EVIDENCE
from signal_lattice.evidence import structure_text as ST
from signal_lattice.evidence.structure_text import AMBIGUOUS, OWNER, RISK, UPSTREAM

FILLER = " This paragraph is long enough to be scanned by the extractor as a real filing paragraph."


def extract(*paragraphs: str):
    return ST.extract_structure("\n".join(p + FILLER for p in paragraphs))


def only(items, kind, direction=None):
    return [i for i in items if i.kind == kind and (direction is None or i.direction == direction)]


class LeadTimeTests(unittest.TestCase):
    def test_owner_lead_time_in_weeks_becomes_months(self):
        items = extract("Our lead times for our products are currently 26 to 30 weeks because our customers place orders far in advance.")
        [item] = only(items, "lead_time")
        self.assertEqual(item.direction, OWNER)
        self.assertAlmostEqual(item.value, 30 * 12 / 52, places=2)
        self.assertAlmostEqual(item.value_low, 26 * 12 / 52, places=2)
        self.assertIn("26 to 30 weeks", item.sentence)

    def test_upstream_lead_time_is_upstream_not_owner(self):
        items = extract("We rely on our suppliers, whose lead times for certain components have extended to 52 weeks.")
        [item] = only(items, "lead_time")
        self.assertEqual(item.direction, UPSTREAM)
        self.assertAlmostEqual(item.value, 12.0, places=1)

    def test_no_subject_cue_is_ambiguous(self):
        [item] = only(extract("Lead times have extended to 40 weeks across the industry, according to trade press."), "lead_time")
        self.assertEqual(item.direction, AMBIGUOUS)

    def test_notice_periods_are_not_lead_times(self):
        self.assertEqual(only(extract("Orders are cancelable by giving notice 31 to 45 days prior to the expected shipment date."), "lead_time"), [])


class SoleSourceTests(unittest.TestCase):
    def test_company_as_sole_source_is_owner(self):
        [item] = only(extract("We are the sole source supplier of this coating to our customers in the aerospace industry."), "sole_source")
        self.assertEqual(item.direction, OWNER)

    def test_depending_on_a_single_source_is_upstream_risk(self):
        [item] = only(extract("We depend on a single-source supplier for certain key components used in our devices."), "sole_source")
        self.assertEqual(item.direction, UPSTREAM)

    def test_generic_noun_without_a_dependency_verb_is_ambiguous(self):
        [item] = only(extract("The Distribution Segment is the largest distributor and single source for tools, equipment and supplies."), "sole_source")
        self.assertEqual(item.direction, AMBIGUOUS)

    def test_sole_source_of_gain_and_no_single_supplier_are_not_supply_statements(self):
        items = extract("Capital appreciation, if any, of our common stock may be your sole source of gain on the investment.",
                        "During the year no single supplier accounted for more than 10% of our raw material purchases.")
        self.assertEqual(only(items, "sole_source"), [])


class PurchaseShareTests(unittest.TestCase):
    def test_single_supplier_share_of_purchases_is_upstream_with_number(self):
        [item] = only(extract("One supplier accounted for 62% of our total inventory purchases during fiscal 2025."), "purchase_share")
        self.assertEqual((item.direction, item.value), (UPSTREAM, 62.0))

    def test_payables_and_negations_do_not_count(self):
        items = extract("There were two vendors that accounted for over 30% of the Company's consolidated accounts payable as of year end.",
                        "In the quarter no single vendor represented more than 10% of our raw inventory purchases.")
        self.assertEqual(only(items, "purchase_share"), [])

    def test_greater_than_threshold_is_flagged_as_lower_bound(self):
        [item] = only(extract("Two suppliers were individually responsible for greater than 10% of the Company's total inventory purchases."), "purchase_share")
        self.assertTrue(item.detail["lower_bound"])


class CustomerConcentrationTests(unittest.TestCase):
    def test_largest_customer_share_is_single_scope(self):
        [item] = only(extract("Our largest customer accounted for 30% of the Company's total net revenues in fiscal 2025."), "customer_concentration")
        self.assertEqual((item.direction, item.value, item.detail["scope"]), (RISK, 30.0, "single"))

    def test_top_n_and_multi_customer_shares_are_not_single(self):
        items = extract("Sales to our ten largest customers accounted for 53% of total net revenues in 2025.",
                        "We derived approximately 29% of our revenue from three customers during 2025.")
        self.assertEqual({i.detail["scope"] for i in only(items, "customer_concentration")}, {"multi"})

    def test_no_customer_over_ten_percent_is_recorded_as_zero(self):
        [item] = only(extract("No customer accounted for more than 10% of our revenue for the years ended December 31, 2025 and 2024."), "customer_concentration")
        self.assertEqual((item.value, item.detail["scope"]), (0.0, "none_over_10pct"))

    def test_geography_receivables_and_negations_are_not_customer_concentration(self):
        items = extract("We derived 60.3% of our revenue from sales to customers outside of the United States in 2025.",
                        "Customer A constituted 21% of the accounts receivable, while Customer B represented 11%.",
                        "Ashland has no operations in any individual international country or single customer that represented more than 10% of sales.",
                        "Approximately 47.6% of our revenue was derived from customers based in the Asia Pacific region.")
        self.assertEqual(only(items, "customer_concentration"), [])

    def test_more_than_ten_percent_is_a_lower_bound(self):
        [item] = only(extract("In fiscal 2025 we had one customer whose net sales accounted for more than 10% of our total net sales."), "customer_concentration")
        self.assertTrue(item.detail["lower_bound"])


class QualificationTests(unittest.TestCase):
    def test_customers_qualifying_a_new_supplier_is_an_owner_moat(self):
        [item] = only(extract("Our customers typically spend 12 to 18 months to qualify a new supplier, which makes switching difficult."), "qualification")
        self.assertEqual(item.direction, OWNER)
        self.assertAlmostEqual(item.value, 18.0)

    def test_us_qualifying_an_alternative_source_is_upstream_risk(self):
        [item] = only(extract("It could take 18 to 24 months to qualify an alternative source for this raw material."), "qualification")
        self.assertEqual(item.direction, UPSTREAM)

    def test_regulatory_qualification_is_ignored(self):
        self.assertEqual(only(extract("We believe our biologic product should qualify for the 12-year period of exclusivity under the BLA."), "qualification"), [])


class CapacityAndBacklogTests(unittest.TestCase):
    def test_own_full_capacity_is_owner(self):
        items = extract("We are currently operating at full capacity in our manufacturing facility and demand exceeds our current capacity.")
        self.assertTrue(only(items, "capacity_constraint", OWNER))

    def test_plant_utilization_number_is_captured(self):
        [item] = only(extract("Our plant utilization was approximately 92% during the year as customer orders remained strong."), "capacity_constraint")
        self.assertEqual((item.direction, item.value), (OWNER, 92.0))

    def test_supplier_capacity_constraint_is_upstream(self):
        [item] = only(extract("Our suppliers are capacity constrained and may not be able to meet our requirements in a timely manner."), "capacity_constraint")
        self.assertEqual(item.direction, UPSTREAM)

    def test_insurance_utilization_and_same_store_full_capacity_are_not_production_capacity(self):
        items = extract("For lifetime withdrawal guarantee riders the assumption is a 100% utilization rate once account value reaches zero.",
                        "Same-store metrics include attractions and lodging properties that we operated at full capacity during the periods.")
        self.assertEqual(only(items, "capacity_constraint"), [])

    def test_backlog_level_with_prior_period(self):
        [item] = only(extract("Our backlog was $3.16 billion at June 30, 2026 compared to $2.64 billion at June 30, 2025."), "backlog")
        self.assertEqual((item.direction, item.value, item.value_low), (OWNER, 3.16e9, 2.64e9))

    def test_backlog_change_amount_and_unitless_table_numbers_are_skipped(self):
        items = extract("Our backlog at June 30, 2025 increased $1.4 million from March 31, 2025.",
                        "Our order backlog was $61,199 as of June 30, 2025 in the table below.")
        self.assertEqual(only(items, "backlog"), [])


class StructureAndCacheTests(unittest.TestCase):
    def test_section_and_paragraph_are_kept(self):
        text = "Item 1A. Risk Factors\n" + "We rely on our suppliers, and we depend on a sole source supplier for key components." + FILLER
        [item] = only(ST.extract_structure(text), "sole_source")
        self.assertTrue(item.section.startswith("Item 1A"))
        self.assertIn("sole source supplier", item.paragraph)

    def test_cache_round_trip_and_version_invalidation(self):
        text = "We depend on a single-source supplier for certain key components used in our devices." + FILLER
        filing = ST.build_filing_extraction(text, cik=7, accession="0000000007-26-000001", form="10-K", filed="2026-03-01",
                                            period_end="2025-12-31", url="https://www.sec.gov/Archives/edgar/data/7/x/y.htm")
        with tempfile.TemporaryDirectory() as tmp:
            cache = ST.ExtractionCache(Path(tmp))
            self.assertIsNone(cache.get(filing.accession))
            cache.put(filing)
            self.assertEqual(cache.get(filing.accession).to_dict(), filing.to_dict())
            old = ST.EXTRACTOR_VERSION
            try:
                ST.EXTRACTOR_VERSION = "structure-text/999"
                self.assertIsNone(cache.get(filing.accession))     # 抽取器升级后旧缓存自动作废
            finally:
                ST.EXTRACTOR_VERSION = old


def evidence(*items, filed="2026-03-02", form="10-K", accession="0001234567-26-000004"):
    filing = ST.FilingExtraction(fx.CIK, accession, form, filed, "2025-12-31",
                                 "https://www.sec.gov/Archives/edgar/data/%d/%s/doc0004.htm" % (fx.CIK, accession.replace("-", "")),
                                 10000, ST.EXTRACTOR_VERSION, tuple(items))
    return SF.StructureEvidence([filing])


def item(kind, direction, value=None, sentence="Synthetic sentence.", **detail):
    return ST.Extraction(kind, direction, sentence, sentence, "Item 1", value, None, None, detail)


class FactorAnchorTests(unittest.TestCase):
    P = B.DEFAULT_PARAMS

    def test_no_extraction_means_no_evidence_not_zero(self):
        empty = evidence()
        for fn in (SF.expansion_lead_time, SF.supplier_concentration, SF.qualification_barrier, SF.customer_diversification,
                   SF.upstream_dependency_risk):
            self.assertIsNone(fn(empty, self.P).rating, fn.__name__)

    def test_lead_time_needs_a_number_and_owner_direction_for_three_or_more(self):
        self.assertEqual(SF.expansion_lead_time(evidence(item("lead_time", OWNER, 7.0)), self.P).rating, 3.0)
        self.assertEqual(SF.expansion_lead_time(evidence(item("lead_time", OWNER, 13.0)), self.P).rating, 4.0)
        self.assertEqual(SF.expansion_lead_time(evidence(item("lead_time", OWNER, 2.96)), self.P).rating, 1.0)
        self.assertIsNone(SF.expansion_lead_time(evidence(item("lead_time", UPSTREAM, 12.0)), self.P).rating)
        self.assertIsNone(SF.expansion_lead_time(evidence(item("lead_time", AMBIGUOUS, 12.0)), self.P).rating)

    def test_upstream_sole_source_never_raises_supplier_concentration(self):
        ev = evidence(item("sole_source", UPSTREAM), item("sole_source", AMBIGUOUS))
        self.assertIsNone(SF.supplier_concentration(ev, self.P).rating)
        self.assertEqual(SF.supplier_concentration(evidence(item("sole_source", OWNER)), self.P).rating, 3.0)

    def test_upstream_dependency_goes_to_risk_with_low_rating(self):
        risk = SF.upstream_dependency_risk(evidence(item("sole_source", UPSTREAM)), self.P)
        self.assertEqual(risk.rating, 2.0)
        heavy = SF.upstream_dependency_risk(evidence(item("sole_source", UPSTREAM), item("purchase_share", UPSTREAM, 62.0)), self.P)
        self.assertEqual(heavy.rating, 1.0)
        boilerplate = SF.upstream_dependency_risk(evidence(item("capacity_constraint", UPSTREAM)), self.P)
        self.assertIsNone(boilerplate.rating)        # 「供应链中断」套话不算具体披露

    def test_low_supplier_share_is_not_a_risk_signal_and_stale_years_do_not_win(self):
        low = evidence(item("purchase_share", UPSTREAM, 11.0, sentence="In 2025, two suppliers accounted for 12% and 11% of purchases."))
        self.assertIsNone(SF.upstream_dependency_risk(low, self.P).rating)
        stale = evidence(item("purchase_share", UPSTREAM, 55.0, sentence="In the year ended December 31, 2023, one supplier accounted for 55% of purchases."),
                         item("purchase_share", UPSTREAM, 11.0, sentence="In the year ended December 31, 2025, one supplier accounted for 11% of purchases."))
        self.assertIsNone(SF.upstream_dependency_risk(stale, self.P).rating)          # 2023 年的 55% 不冒充当前状态
        current = evidence(item("purchase_share", UPSTREAM, 55.0, sentence="In the year ended December 31, 2025, one supplier accounted for 55% of purchases."))
        self.assertEqual(SF.upstream_dependency_risk(current, self.P).rating, 1.0)

    def test_customer_share_uses_the_most_recent_year(self):
        old = item("customer_concentration", RISK, 36.0, sentence="Our largest customer accounted for 36% in 2023.", scope="single")
        new = item("customer_concentration", RISK, 12.0, sentence="Our largest customer accounted for 12% in 2025.", scope="single")
        self.assertEqual(SF.customer_diversification(evidence(old, new), self.P).rating, 3.0)

    def test_qualification_barrier_anchors(self):
        self.assertEqual(SF.qualification_barrier(evidence(item("qualification", OWNER, 18.0)), self.P).rating, 3.0)
        self.assertEqual(SF.qualification_barrier(evidence(item("qualification", OWNER, 30.0)), self.P).rating, 4.0)
        self.assertIsNone(SF.qualification_barrier(evidence(item("qualification", UPSTREAM, 24.0)), self.P).rating)

    def test_customer_diversification_anchors(self):
        rate = lambda v, scope="single": SF.customer_diversification(evidence(item("customer_concentration", RISK, v, scope=scope)), self.P).rating
        self.assertEqual(rate(0.0, "none_over_10pct"), 4.0)
        self.assertEqual(rate(12.0), 3.0)
        self.assertEqual(rate(30.0), 2.0)
        self.assertEqual(rate(45.0), 1.0)
        self.assertEqual(rate(70.0), 0.0)
        self.assertIsNone(rate(53.0, "multi"))

    def test_owner_tightness_needs_utilization_number_for_three(self):
        marker = SF.owner_tightness(evidence(item("capacity_constraint", OWNER)), self.P)
        self.assertEqual(marker[1], 2.0)
        util = SF.owner_tightness(evidence(item("capacity_constraint", OWNER, 95.0)), self.P)
        self.assertEqual(util[1], 3.0)
        self.assertIsNone(SF.owner_tightness(evidence(item("capacity_constraint", AMBIGUOUS), item("capacity_constraint", UPSTREAM)), self.P))

    def test_every_scored_extraction_carries_an_sec_link_and_the_sentence(self):
        result = SF.expansion_lead_time(evidence(item("lead_time", OWNER, 9.0, sentence="Lead times are 9 months.")), self.P)
        [ref] = result.refs
        self.assertTrue(ref.is_primary_link)
        self.assertIn("Lead times are 9 months.", ref.label)
        self.assertEqual(ref.accession, "0001234567-26-000004")


class BottleneckIntegrationTests(unittest.TestCase):
    AS_OF = "2026-09-15"

    def setUp(self):
        self.store = fx.build_store()

    def score(self, structure=None):
        return B.score_bottleneck(self.store, fx.market(), self.AS_OF, B.DEFAULT_PARAMS, [], None, None, None, structure)

    def test_structure_replaces_direction_blind_markers_and_no_hits_stay_no_evidence(self):
        d = self.score(evidence()).detail
        for name in ("supplier_concentration", "expansion_lead_time", "qualification_barrier"):
            self.assertEqual(d["factors"]["constraint"][name]["rating"], NO_EVIDENCE, name)
        self.assertEqual(d["factors"]["investability"]["customer_diversification"]["rating"], NO_EVIDENCE)
        self.assertEqual(d["structure_text"]["counts"], {})

    def test_owner_evidence_lifts_constraint_factors_and_links_flow_into_the_receipt(self):
        ev = evidence(item("lead_time", OWNER, 14.0, sentence="Our lead times are about 14 months."),
                      item("qualification", OWNER, 20.0, sentence="Customers need 20 months to qualify a new supplier."),
                      item("customer_concentration", RISK, 12.0, sentence="One customer accounted for 12% of revenue.", scope="single"))
        base, with_structure = self.score(evidence()), self.score(ev)
        factors = with_structure.detail["factors"]
        self.assertEqual(factors["constraint"]["expansion_lead_time"]["rating"], 4.0)
        self.assertEqual(factors["constraint"]["qualification_barrier"]["rating"], 3.0)
        self.assertEqual(factors["investability"]["customer_diversification"]["rating"], 3.0)
        self.assertGreater(with_structure.detail["dimensions"]["constraint"]["coverage"], base.detail["dimensions"]["constraint"]["coverage"])
        url = factors["constraint"]["expansion_lead_time"]["refs"][0]["url"]
        self.assertIn(url, {link["url"] for link in with_structure.detail["primary_links"]})
        self.assertIn("Our lead times are about 14 months.", factors["constraint"]["expansion_lead_time"]["refs"][0]["label"])

    def test_upstream_single_source_lowers_investability_and_never_touches_constraint(self):
        ev = evidence(item("sole_source", UPSTREAM, sentence="We depend on a single-source supplier."),
                      item("purchase_share", UPSTREAM, 62.0, sentence="One supplier was 62% of purchases."))
        base, risky = self.score(evidence()), self.score(ev)
        self.assertEqual(risky.detail["factors"]["investability"]["technology_resilience"]["rating"], 1.0)
        self.assertEqual(risky.detail["factors"]["constraint"]["supplier_concentration"]["rating"], NO_EVIDENCE)
        self.assertEqual(risky.detail["dimensions"]["constraint"]["score"], base.detail["dimensions"]["constraint"]["score"])
        self.assertTrue(risky.detail["structure_text"]["risks"])

    def test_backlog_text_backs_funded_demand_only_when_xbrl_rpo_is_absent(self):
        ev = evidence(ST.Extraction("backlog", OWNER, "Our backlog was $400 million.", "p", "Item 7", 400e6, 300e6, "usd", {}))
        weak_store = fx.build_store(fx.weak_company_facts())
        r = B.score_bottleneck(weak_store, fx.market(), self.AS_OF, B.DEFAULT_PARAMS, [], None, None, None, ev)
        self.assertIn("原文积压", r.detail["factors"]["constraint"]["funded_demand"]["basis"])
        strong = self.score(ev)
        self.assertNotIn("原文积压", strong.detail["factors"]["constraint"]["funded_demand"]["basis"])   # 有 XBRL RPO 就用 RPO

    def test_structure_filed_after_as_of_is_rejected(self):
        with self.assertRaises(ValueError):
            self.score(evidence(item("lead_time", OWNER, 9.0), filed="2026-10-01"))

    def test_without_structure_old_marker_behaviour_is_unchanged(self):
        r = B.score_bottleneck(self.store, fx.market(), self.AS_OF, B.DEFAULT_PARAMS, [], None, None)
        self.assertIsNone(r.detail["structure_text"])
        self.assertEqual(r.detail["factors"]["constraint"]["supplier_concentration"]["rating"], NO_EVIDENCE)


if __name__ == "__main__":
    unittest.main()
