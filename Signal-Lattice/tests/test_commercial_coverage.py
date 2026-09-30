"""商业机会分支的取数口径扩展（COMMERCIAL_PROFILE）：金融业营收、新债务标签、营收断更检查、独立的经营现金流。
全部用自造的合成 companyfacts（branch_fixtures），不联网。铁律：默认口径（瓶颈等其它分支用）的结果不变；
只用 as_of 之前已申报的数；拿不到就是 NO_EVIDENCE，不填中值。"""

from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import branch_fixtures as fx
from signal_lattice import branch_entries as BE
from signal_lattice import research_cycle as RC
from signal_lattice.branches import commercial as C
from signal_lattice.branches import sec_inputs
from signal_lattice.branches.fundamentals import (COMMERCIAL_PROFILE, DEFAULT_PROFILE, NEEDED_CONCEPTS, compute_fundamentals)
from signal_lattice.branches.scoring_support import NO_EVIDENCE
from signal_lattice.evidence.factstore import FactStore

AS_OF = "2026-09-15"
H126 = fx.ACC[("2026-06-30", "10-Q")]


def bank_facts(drop_nonint_h126: bool = False) -> dict:
    """银行：没有任何营收标签，只有净利息收入 + 非利息收入。"""
    us = dict([
        fx._flow("InterestIncomeExpenseNet", {"FY24": 80e6, "H124": 38e6, "FY25": 90e6, "H125": 43e6, "H126": 50e6}),
        fx._flow("NoninterestIncome", {"FY24": 20e6, "H124": 9e6, "FY25": 22e6, "H125": 10e6, "H126": 13e6}),
        fx._flow("NetCashProvidedByUsedInOperatingActivities", {"FY24": 30e6, "H124": 14e6, "FY25": 35e6, "H125": 16e6, "H126": 20e6}),
        fx._instant("CashAndCashEquivalentsAtCarryingValue", {"2025-06-30": 100e6, "2025-12-31": 110e6, "2026-06-30": 120e6}),
    ])
    if drop_nonint_h126:
        us["NoninterestIncome"]["units"]["USD"] = [e for e in us["NoninterestIncome"]["units"]["USD"] if e["accn"] != H126]
    shares = dict([fx._instant("EntityCommonStockSharesOutstanding", {"2025-06-30": 20e6, "2026-06-30": 20e6}, "shares")])
    return {"facts": {"us-gaap": us, "dei": shares}}


def without(facts: dict, tag: str, accession: str) -> dict:
    out = copy.deepcopy(facts)
    body = out["facts"]["us-gaap"][tag]
    body["units"]["USD"] = [e for e in body["units"]["USD"] if e["accn"] != accession]
    return out


def compute(store, profile, as_of=AS_OF):
    return compute_fundamentals(store, fx.market(as_of=as_of), as_of, profile)


class DefaultProfileIsUnchangedTests(unittest.TestCase):
    def test_default_and_commercial_profiles_agree_on_an_ordinary_company(self):
        store = fx.build_store()
        a, b = compute(store, DEFAULT_PROFILE), compute(store, COMMERCIAL_PROFILE)
        for name in ("revenue_ttm", "revenue_yoy", "gross_margin", "gm_change_bps", "ocf_ttm", "ocf_margin", "rpo", "debt",
                     "net_cash", "share_change_yoy", "cap_sales"):
            self.assertEqual(getattr(a, name), getattr(b, name), name)
        self.assertEqual((a.profile_name, b.profile_name), ("default", "commercial"))

    def test_default_profile_still_cannot_see_bank_revenue(self):
        self.assertFalse(compute(fx.build_store(bank_facts()), DEFAULT_PROFILE).revenue_ttm.ok)

    def test_default_profile_keeps_the_old_debt_concepts_only(self):
        self.assertNotIn("us-gaap:LongTermDebtAndCapitalLeaseObligations", DEFAULT_PROFILE.debt_noncurrent)
        self.assertIn("us-gaap:LongTermDebtAndCapitalLeaseObligations", COMMERCIAL_PROFILE.debt_noncurrent)

    def test_needed_concepts_contain_every_part_of_the_extended_profile(self):
        for concept in ("us-gaap:InterestIncomeExpenseNet", "us-gaap:NoninterestIncome", "us-gaap:RevenuesNetOfInterestExpense",
                        "us-gaap:LongTermDebtAndCapitalLeaseObligations", "us-gaap:LongTermDebtAndCapitalLeaseObligationsCurrent",
                        "us-gaap:DebtAndCapitalLeaseObligations"):
            self.assertIn(concept, NEEDED_CONCEPTS)


class BankRevenueTests(unittest.TestCase):
    def test_bank_net_revenue_is_net_interest_plus_noninterest_income_with_sec_links(self):
        f = compute(fx.build_store(bank_facts()), COMMERCIAL_PROFILE)
        # TTM@2026-06-30 = FY25 + H1'26 - H1'25，两项相加：(90+22) + (50+13) - (43+10) = 122e6
        self.assertAlmostEqual(f.revenue_ttm.value, 122e6)
        self.assertAlmostEqual(f.revenue_ttm_prior.value, ((80 + 20) + (43 + 10) - (38 + 9)) * 1e6)     # FY24 + H1'25 - H1'24
        self.assertAlmostEqual(f.revenue_yoy.value, 122e6 / 106e6 - 1)
        self.assertTrue(f.revenue_ttm.refs)
        for ref in f.revenue_ttm.refs:
            self.assertRegex(ref.url, r"^https://www\.sec\.gov/Archives/edgar/data/1234567/")
            self.assertLessEqual(ref.filed, AS_OF)
            self.assertIn("InterestIncomeExpenseNet+us-gaap:NoninterestIncome", ref.label)

    def test_a_missing_component_for_a_period_means_no_revenue_for_that_period_not_a_half_sum(self):
        store = fx.build_store(bank_facts(drop_nonint_h126=True))
        f = compute(store, COMMERCIAL_PROFILE)
        # H1'26 缺非利息收入 -> 最新 TTM 拼不出；退到 FY25 那一期，但它比最近一份 10-Q（2026-06-30）早 181 天 -> 按断更处理
        self.assertFalse(f.revenue_ttm.ok)
        self.assertTrue(any(n.startswith("REVENUE_TTM_STALE") for n in f.notes))

    def test_bank_gets_a_scored_exposure_and_the_rating_is_the_revenue_level_one(self):
        store = fx.build_store(bank_facts())
        r = C.score_commercial(store, fx.market(), AS_OF, C.DEFAULT_PARAMS, [], None)
        exp = r.detail["base_dimensions"]["issuer_exposure_attribution"]
        self.assertEqual(exp["rating"], C.DEFAULT_PARAMS["exposure"]["revenue_only_rating"])
        self.assertEqual(r.detail["base_dimensions"]["expectations_variant"]["rating"], NO_EVIDENCE)

    def test_sum_needs_both_parts_in_the_same_filing(self):
        facts = bank_facts()
        for e in facts["facts"]["us-gaap"]["NoninterestIncome"]["units"]["USD"]:
            if e["accn"] == H126:
                e["accn"] = "0001234567-26-000099"            # 另一份申报（不同 accession）
        f = compute(fx.build_store(facts), COMMERCIAL_PROFILE)
        self.assertFalse(f.revenue_ttm.ok)


class PointInTimeTests(unittest.TestCase):
    def test_bank_revenue_uses_only_filings_visible_at_as_of(self):
        store = fx.build_store(bank_facts())
        early = compute(store, COMMERCIAL_PROFILE, "2026-07-15")    # H1'26 的 10-Q 2026-08-04 才申报
        late = compute(store, COMMERCIAL_PROFILE, AS_OF)
        self.assertAlmostEqual(early.revenue_ttm.value, 90e6 + 22e6)          # 只有 FY25
        self.assertAlmostEqual(late.revenue_ttm.value, 122e6)
        for ref in early.revenue_ttm.refs:
            self.assertLessEqual(ref.filed, "2026-07-15")

    def test_future_filing_does_not_change_an_earlier_commercial_receipt(self):
        as_of = "2026-07-15"
        a = C.score_commercial(fx.build_store(bank_facts()), fx.market(as_of=as_of), as_of, C.DEFAULT_PARAMS, [], None)
        b = C.score_commercial(fx.build_store(bank_facts(), drop_accessions=(H126,)), fx.market(as_of=as_of), as_of,
                               C.DEFAULT_PARAMS, [], None)
        self.assertEqual(a.to_dict(), b.to_dict())


class StaleRevenueTests(unittest.TestCase):
    def setUp(self):
        self.facts = without(fx.strong_company_facts(), "Revenues", H126)       # 营收标签在最新 10-Q 里不再出现

    def test_commercial_profile_refuses_to_present_old_revenue_as_current(self):
        store = fx.build_store(self.facts)
        self.assertTrue(compute(store, DEFAULT_PROFILE).revenue_ttm.ok)              # 旧口径：拿 2025-12-31 的 TTM 当现值
        f = compute(store, COMMERCIAL_PROFILE)
        self.assertFalse(f.revenue_ttm.ok)
        self.assertIsNone(f.ttm_end)
        self.assertEqual(f.annual_revenue_growth, ())
        self.assertTrue(any(n.startswith("REVENUE_TTM_STALE:ttm_end=2025-12-31") for n in f.notes))
        r = C.score_commercial(store, fx.market(), AS_OF, C.DEFAULT_PARAMS, [], None)
        self.assertEqual(r.detail["base_dimensions"]["issuer_exposure_attribution"]["rating"], NO_EVIDENCE)

    def test_one_quarter_lag_is_still_accepted(self):
        facts = without(fx.strong_company_facts(), "Revenues", H126)
        # 最近一份 10-Q 的报告期 2026-06-30 与营收 TTM 截止 2026-03-31 相差 91 天 <= 100：仍算当前
        q1 = fx.ACC[("2026-03-31", "10-Q")]
        entries = facts["facts"]["us-gaap"]["Revenues"]["units"]["USD"]
        entries += [{"start": "2026-01-01", "end": "2026-03-31", "val": 200e6, "accn": q1, "form": "10-Q", "filed": fx.FILED[q1], "fp": "Q1", "fy": 2026},
                    {"start": "2025-01-01", "end": "2025-03-31", "val": 130e6, "accn": q1, "form": "10-Q", "filed": fx.FILED[q1], "fp": "Q1", "fy": 2026}]
        f = compute(fx.build_store(facts), COMMERCIAL_PROFILE)
        self.assertTrue(f.revenue_ttm.ok)
        self.assertEqual(f.ttm_end, "2026-03-31")


class StandaloneOperatingCashFlowTests(unittest.TestCase):
    def test_fresh_operating_cash_flow_is_kept_when_revenue_went_stale_but_margin_needs_the_same_end(self):
        store = fx.build_store(without(fx.strong_company_facts(), "Revenues", H126))
        old, new = compute(store, DEFAULT_PROFILE), compute(store, COMMERCIAL_PROFILE)
        self.assertFalse(old.ocf_ttm.ok)                      # 旧口径：必须与营收同一截止日，营收断更就连现金流一起丢
        self.assertTrue(new.ocf_ttm.ok)
        self.assertAlmostEqual(new.ocf_ttm.value, 140e6 + 125e6 - 65e6)
        self.assertFalse(new.ocf_margin.ok)                   # 营收没有，营收率自然没有
        r = C.score_commercial(store, fx.market(), AS_OF, C.DEFAULT_PARAMS, [], None)
        self.assertNotEqual(r.detail["base_dimensions"]["durability_balance_sheet"]["rating"], NO_EVIDENCE)

    def test_stale_operating_cash_flow_is_rejected(self):
        facts = fx.strong_company_facts()
        ocf = facts["facts"]["us-gaap"]["NetCashProvidedByUsedInOperatingActivities"]["units"]["USD"]
        ocf[:] = [e for e in ocf if e["accn"] not in (H126, fx.ACC[("2025-12-31", "10-K")], fx.ACC[("2025-06-30", "10-Q")])]
        f = compute(fx.build_store(facts), COMMERCIAL_PROFILE)
        self.assertFalse(f.ocf_ttm.ok)                        # 最新可拼的现金流 TTM 截止 2024-12-31，离最近报告期远超 100 天

    def test_margin_and_fcf_only_when_ends_align(self):
        f = compute(fx.build_store(), COMMERCIAL_PROFILE)
        self.assertTrue(f.ocf_margin.ok)
        self.assertTrue(f.fcf_ttm.ok)


class DebtLabelTests(unittest.TestCase):
    def _facts(self):
        facts = fx.strong_company_facts()
        tags = facts["facts"]["us-gaap"]
        tags["LongTermDebtAndCapitalLeaseObligations"] = tags.pop("LongTermDebt")      # 只用新标签
        return facts

    def test_new_debt_label_is_read_by_the_commercial_profile_only(self):
        store = fx.build_store(self._facts())
        old, new = compute(store, DEFAULT_PROFILE), compute(store, COMMERCIAL_PROFILE)
        self.assertTrue(old.debt_assumed_zero)                # 旧口径不认识这个标签：按「无债务」估算（代理，评分封顶）
        self.assertFalse(new.debt_assumed_zero)
        self.assertAlmostEqual(new.debt.value, 30e6)
        self.assertAlmostEqual(new.net_cash.value, 330e6 - 30e6)
        self.assertTrue(new.debt.refs and all(r.url.startswith("https://www.sec.gov/") for r in new.debt.refs))


class CommercialReceiptsEntryTests(unittest.TestCase):
    def test_receipts_recompute_default_profile_fundamentals_with_the_commercial_profile(self):
        store = fx.build_store(bank_facts())
        funds = {"SYNS": compute(store, DEFAULT_PROFILE)}
        self.assertFalse(funds["SYNS"].revenue_ttm.ok)
        receipts = BE.commercial_receipts(store, funds, C.DEFAULT_PARAMS, [], AS_OF)
        self.assertNotEqual(receipts["SYNS"].detail["base_dimensions"]["issuer_exposure_attribution"]["rating"], NO_EVIDENCE)

    def test_factor_no_evidence_table_has_all_eighteen_factors(self):
        store = fx.build_store()
        receipts = BE.commercial_receipts(store, {"SYNS": compute(store, COMMERCIAL_PROFILE)}, C.DEFAULT_PARAMS, [], AS_OF)
        table = BE.commercial_factor_no_evidence(receipts)
        self.assertEqual(set(table["base"]), set(C.BASE_DIMENSIONS))
        self.assertEqual(set(table["risk"]), set(C.RISK_FACTORS))
        self.assertEqual(table["base"]["expectations_variant"], 1.0)       # 永远 NO_EVIDENCE：没有一手的一致预期


class ConceptSetBackfillTests(unittest.TestCase):
    def test_marker_changes_with_the_concept_set(self):
        self.assertNotEqual(sec_inputs.concept_set_marker(), sec_inputs.concept_set_marker(NEEDED_CONCEPTS[:-1]))
        self.assertEqual(sec_inputs.concept_set_marker(), sec_inputs.concept_set_marker(reversed(NEEDED_CONCEPTS)))

    def test_missing_ciks_are_listed_until_marked(self):
        store = FactStore(":memory:")
        marker = sec_inputs.concept_set_marker()
        self.assertEqual(sec_inputs.ciks_missing_concept_set(store, [1, 2], marker), [1, 2])
        sec_inputs.mark_concept_set(store, 1, marker, "2026-09-29")
        self.assertEqual(sec_inputs.ciks_missing_concept_set(store, [1, 2], marker), [2])

    def _cycle(self, facts, client):
        events = mock.MagicMock()
        events.db.execute.return_value.fetchone.return_value = [None]
        events.db.execute.return_value.fetchall.return_value = []
        ec = mock.MagicMock()
        ec.dera_coverage_end.return_value = "2026-06-30"
        ec.stage_dera.return_value, ec.stage_form4.return_value = {}, {}
        cfg = RC.CycleConfig(project_root=Path("."), work_dir=Path(tempfile.mkdtemp()), out_dir=Path(tempfile.mkdtemp()),
                             facts_db=Path("f"), events_db=Path("e"), bars_dir=Path("b"), text_cache_dir=Path("t"),
                             structure_cache_dir=Path("s"), sec_cache_dir=Path("c"))
        return RC.LiveHooks()._incremental_sec(cfg, client, facts, events, [1, 2], date(2026, 9, 29), lambda x: x, ec, lambda m: None)

    def test_companyfacts_are_refetched_once_after_the_concept_set_changes(self):
        facts, client = FactStore(":memory:"), mock.MagicMock()
        client.companyfacts.return_value = {"facts": {}}
        first = self._cycle(facts, client)
        self.assertEqual(first["companyfacts_concept_backfill"], 2)
        self.assertEqual(client.companyfacts.call_count, 2)
        second = self._cycle(facts, client)
        self.assertEqual(second["companyfacts_concept_backfill"], 0)
        self.assertEqual(client.companyfacts.call_count, 2)            # 标记过的公司不再重取


if __name__ == "__main__":
    unittest.main()
