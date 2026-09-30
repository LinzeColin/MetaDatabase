"""中枢：支持度、独立性去重、一票否决、失效条件、NO_ACTION 观察名单、SYSTEM_BLOCKED。

每个测试只动一处，其余是 hub_fixtures.standard_pool()：ALPHA = 事件航图 PASS(1.0) + 商业机会排序支持(0.3) = 1.3，
恰好过线；BETA = 只有事件航图 PASS(1.0)。
"""

import json
import unittest
from copy import deepcopy
from datetime import timedelta

from signal_lattice import hub
from signal_lattice.research_view import ResearchView
from hub_fixtures import (BOTTLENECK, COMMERCIAL, EVENT, FORESIGHT, NOW, build_view, filler, fresh_market, record, run_decision,
                          sec_link, standard_pool)


def decision_of(outcome):
    return outcome["decision"]


class SupportTests(unittest.TestCase):
    def test_pass_is_1_and_top_decile_rank_is_0_3_and_the_rest_is_0(self):
        view = build_view(standard_pool())
        alpha = {i["branch_id"]: i for i in hub.support_summary(view, "ALPHA", hub.branch_weights(None))["all"]}
        self.assertEqual((alpha[EVENT]["kind"], alpha[EVENT]["raw"]), ("PASS", 1.0))
        self.assertEqual((alpha[COMMERCIAL]["kind"], alpha[COMMERCIAL]["raw"]), ("RANK", 0.3))
        self.assertEqual(alpha[BOTTLENECK]["raw"], 0.0)                       # 分数 3.0 不在瓶颈全池前 10%
        self.assertEqual(alpha[FORESIGHT]["raw"], 0.0)                        # 整分支 ABSTAIN
        beta = {i["branch_id"]: i for i in hub.support_summary(view, "BETA", hub.branch_weights(None))["all"]}
        self.assertEqual(beta[COMMERCIAL]["raw"], 0.0)                        # 5.0 不在前 10%

    def test_alpha_reaches_exactly_the_publish_threshold(self):
        summary = hub.support_summary(build_view(standard_pool()), "ALPHA", hub.branch_weights(None))
        self.assertAlmostEqual(summary["total"], 1.3)
        self.assertTrue(summary["meets_threshold"])
        self.assertEqual((summary["n_pass"], summary["n_rank"]), (1, 1))

    def test_a_failed_verdict_never_counts_as_rank_support_even_with_a_top_score(self):
        pool = standard_pool()
        pool[COMMERCIAL][0] = record("ALPHA", "FAILED", label="REJECT", score=90.0, links=[sec_link("0000000002-26-000002", cik=11, supports="x")])
        summary = hub.support_summary(build_view(pool), "ALPHA", hub.branch_weights(None))
        self.assertEqual(summary["total"], 1.0)
        self.assertFalse(summary["meets_threshold"])

    def test_a_branch_that_abstained_as_a_whole_gives_no_support(self):
        view = build_view(standard_pool(), statuses={COMMERCIAL: "ABSTAIN"})
        self.assertEqual(hub.support_summary(view, "ALPHA", hub.branch_weights(None))["total"], 1.0)

    def test_a_claim_without_a_sec_primary_source_is_not_scored(self):
        pool = standard_pool()
        pool[COMMERCIAL][0] = record("ALPHA", "ABSTAIN", label="SCREEN_FLAG", score=90.0, links=[])
        summary = hub.support_summary(build_view(pool), "ALPHA", hub.branch_weights(None))
        self.assertEqual(summary["total"], 1.0)
        item = next(i for i in summary["all"] if i["branch_id"] == COMMERCIAL)
        self.assertEqual(item["kind"], "NO_PRIMARY_SOURCE")

    def test_non_sec_links_are_not_primary_sources(self):
        pool = standard_pool()
        pool[COMMERCIAL][0] = record("ALPHA", "ABSTAIN", score=90.0, links=[{"url": "https://example.com/report", "supports": "x"}])
        self.assertEqual(hub.support_summary(build_view(pool), "ALPHA", hub.branch_weights(None))["total"], 1.0)

    def test_rank_cutoff_is_the_top_ten_percent_of_the_whole_pool(self):
        view = build_view(standard_pool())
        table = view.ranks[COMMERCIAL]
        self.assertEqual(table["pool"], 22)
        self.assertEqual(table["k"], 3)                                        # ceil(10% x 22)
        self.assertEqual(table["rank"]["ALPHA"], 1)


class IndependenceTests(unittest.TestCase):
    def shared_pool(self):
        """事件航图 PASS 与商业机会排序支持，主证据是同一份申报（同一个 accession）。"""
        pool = standard_pool()
        same = sec_link("0000000001-26-000001", cik=11, supports="INSIDER_BUY_OPPORTUNISTIC")
        pool[COMMERCIAL][0] = record("ALPHA", "ABSTAIN", label="SCREEN_FLAG", score=90.0, links=[same])
        return pool

    def test_two_branches_citing_only_the_same_accession_count_once(self):
        summary = hub.support_summary(build_view(self.shared_pool()), "ALPHA", hub.branch_weights(None))
        self.assertEqual(summary["total"], 1.0)
        self.assertEqual([i["branch_id"] for i in summary["duplicates"]], [COMMERCIAL])
        self.assertFalse(summary["meets_threshold"])

    def test_no_recommendation_and_the_watchlist_says_why(self):
        outcome = run_decision(build_view(self.shared_pool()))
        decision = decision_of(outcome)
        self.assertEqual(decision["state"], "NO_ACTION")
        alpha = next(w for w in decision["watchlist"] if w["symbol"] == "ALPHA")
        self.assertIn("同一份申报", alpha["sentence"])

    def test_the_dedupe_is_by_accession_not_by_url_shape(self):
        pool = self.shared_pool()
        pool[COMMERCIAL][0] = record("ALPHA", "ABSTAIN", score=90.0, links=[
            sec_link("0000000001-26-000001", cik=11, dashed=False).__class__({"url": "https://www.sec.gov/Archives/edgar/data/11/000000000126000001/x-20260630.htm", "supports": "y"})])
        summary = hub.support_summary(build_view(pool), "ALPHA", hub.branch_weights(None))
        self.assertEqual(summary["total"], 1.0)

    def test_partially_overlapping_evidence_still_counts_as_independent(self):
        pool = standard_pool()
        pool[COMMERCIAL][0] = record("ALPHA", "ABSTAIN", score=90.0, links=[
            sec_link("0000000001-26-000001", cik=11, supports="x"), sec_link("0000000009-26-000009", cik=11, supports="y")])
        summary = hub.support_summary(build_view(pool), "ALPHA", hub.branch_weights(None))
        self.assertAlmostEqual(summary["total"], 1.3)
        self.assertEqual(summary["duplicates"], [])

    def test_a_freshness_only_link_is_not_evidence_when_the_branch_has_others(self):
        links = [sec_link("0000000005-26-000005", supports="freshness"), sec_link("0000000006-26-000006", supports="funded_demand")]
        _sec, roots = hub.evidence_roots(links)
        self.assertEqual(roots, ["0000000006-26-000006"])
        _sec, only = hub.evidence_roots(links[:1])
        self.assertEqual(only, ["0000000005-26-000005"])


class WeightTests(unittest.TestCase):
    def test_fewer_than_8_settled_samples_means_equal_weight_and_the_formula_is_reported(self):
        weights = hub.branch_weights({COMMERCIAL: {"n": 7, "hits": 0}})
        self.assertEqual(weights["mode"], "COLD_START_EQUAL")
        self.assertEqual(weights["branches"][COMMERCIAL]["weight"], 1.0)
        self.assertIn("命中率", weights["formula"])

    def test_hit_rate_below_half_lowers_the_weight_and_raises_the_bar(self):
        weights = hub.branch_weights({COMMERCIAL: {"n": 8, "hits": 2}})
        self.assertAlmostEqual(weights["branches"][COMMERCIAL]["weight"], 0.5)
        outcome = run_decision(build_view(standard_pool()), weights=weights)
        decision = decision_of(outcome)
        self.assertEqual(decision["state"], "NO_ACTION")                       # 1.0 + 0.3 x 0.5 = 1.15 < 1.3

    def test_weights_never_exceed_one_so_they_can_not_lower_the_bar(self):
        weights = hub.branch_weights({EVENT: {"n": 10, "hits": 10}})
        self.assertEqual(weights["branches"][EVENT]["weight"], 1.0)
        self.assertEqual(hub.branch_weights({EVENT: {"n": 8, "hits": 4}})["branches"][EVENT]["weight"], 1.0)


class DecisionTests(unittest.TestCase):
    def test_recommendation_for_the_top_candidate_with_reasons_and_sec_links(self):
        outcome = run_decision(build_view(standard_pool()))
        decision = decision_of(outcome)
        self.assertEqual(decision["state"], "RECOMMENDATION")
        self.assertEqual(decision["primary_symbol"], "ALPHA")
        self.assertEqual(decision["action"], "研究跟进（看多）")
        self.assertEqual(decision["action_code"], "RESEARCH_FOLLOW_LONG")
        self.assertEqual({r["branch_id"] for r in decision["reasons"]}, {EVENT, COMMERCIAL})
        self.assertTrue(all(r["sentence"] for r in decision["reasons"]))
        self.assertTrue(decision["sources"])
        self.assertTrue(all(s["url"].startswith("https://www.sec.gov/") for s in decision["sources"]))

    def test_the_wording_is_research_follow_up_never_buy(self):
        text = json.dumps(decision_of(run_decision(build_view(standard_pool()))), ensure_ascii=False)
        self.assertNotIn("买入 ALPHA", text)
        self.assertNotIn('"action": "买入"', text)
        self.assertEqual(hub.ACTION_FOLLOW, "研究跟进（看多）")

    def test_a_lone_pass_is_no_action_and_the_watchlist_has_at_most_five_with_a_gate_each(self):
        pool = standard_pool()
        pool[COMMERCIAL][0] = record("ALPHA", "ABSTAIN", score=1.0, links=[sec_link("0000000002-26-000002", cik=11, supports="x")])
        for i in range(8):
            pool[EVENT].append(record("P%d" % i, "PASS", score=50.0 - i, links=[sec_link("00000001%02d-26-000001" % i, cik=100 + i, date="2026-09-%02d" % (20 + i))]))
        decision = decision_of(run_decision(build_view(pool)))
        self.assertEqual(decision["state"], "NO_ACTION")
        self.assertEqual(decision["action_code"], "NO_ACTION")
        self.assertIsNone(decision["action"])
        self.assertEqual(len(decision["watchlist"]), 5)
        self.assertTrue(all(w["sentence"].startswith("差在【") for w in decision["watchlist"]))
        self.assertTrue(all(w["support_total"] == 1.0 for w in decision["watchlist"]))
        # 同分按事件新近度：最新的申报在前
        self.assertEqual(decision["watchlist"][0]["symbol"], "P7")

    def test_no_action_still_names_the_closest_candidate(self):
        decision = decision_of(run_decision(build_view(standard_pool(), statuses={COMMERCIAL: "ABSTAIN"})))
        self.assertEqual(decision["state"], "NO_ACTION")
        self.assertIn("支持度", decision["rationale"])

    def test_equal_support_is_broken_by_the_more_recent_event(self):
        pool = standard_pool()
        pool[EVENT].append(record("GAMMA", "PASS", score=60.0, links=[sec_link("0000000007-26-000007", cik=13, date="2026-09-28")]))
        pool[COMMERCIAL].append(record("GAMMA", "ABSTAIN", score=95.0, links=[sec_link("0000000008-26-000008", cik=13, supports="x")]))
        decision = decision_of(run_decision(build_view(pool)))
        self.assertEqual(decision["primary_symbol"], "GAMMA")                  # 与 ALPHA 同为 1.3，GAMMA 的事件是 9 月 28 日、更新

    def test_higher_support_beats_recency(self):
        pool = standard_pool()
        pool[BOTTLENECK][0] = record("ALPHA", "PASS", label="INVESTABLE", score=80.0, links=[sec_link("0000000010-26-000010", cik=11, supports="funded_demand")])
        pool[EVENT].append(record("GAMMA", "PASS", score=60.0, links=[sec_link("0000000007-26-000007", cik=13, date="2026-09-29")]))
        pool[COMMERCIAL].append(record("GAMMA", "ABSTAIN", score=95.0, links=[sec_link("0000000008-26-000008", cik=13, supports="x")]))
        summary = hub.support_summary(build_view(pool), "ALPHA", hub.branch_weights(None))
        self.assertAlmostEqual(summary["total"], 2.3)
        self.assertEqual(decision_of(run_decision(build_view(pool)))["primary_symbol"], "ALPHA")

    def test_same_input_same_output(self):
        first = run_decision(build_view(standard_pool()))
        second = run_decision(build_view(standard_pool()))
        self.assertEqual(json.dumps(first, sort_keys=True, default=str), json.dumps(second, sort_keys=True, default=str))


class HardGateTests(unittest.TestCase):
    def test_stale_quote_fails_the_quote_gate_and_the_next_candidate_is_considered(self):
        pool = standard_pool()
        pool[EVENT].append(record("GAMMA", "PASS", score=60.0, links=[sec_link("0000000007-26-000007", cik=13, date="2026-09-01")]))
        pool[COMMERCIAL].append(record("GAMMA", "ABSTAIN", score=95.0, links=[sec_link("0000000008-26-000008", cik=13, supports="x")]))
        view = build_view(pool)
        market = fresh_market([e["symbol"] for e in view.shortlist])
        market["GAMMA"] = {"price": None, "quote_status": "QUOTE_SOURCE_STALE", "source_time": None}
        decision = decision_of(run_decision(view, market=market))
        self.assertEqual(decision["primary_symbol"], "ALPHA")
        gamma = next(c for c in run_decision(view, market=market)["candidates"] if c["symbol"] == "GAMMA")
        self.assertFalse(gamma["gates"]["quote"]["ok"])
        self.assertIn("实时报价", gamma["gate_summary"])

    def test_missing_quote_blocks_that_candidate_only(self):
        view = build_view(standard_pool())
        market = fresh_market([e["symbol"] for e in view.shortlist])
        del market["ALPHA"]
        outcome = run_decision(view, market=market)
        self.assertEqual(decision_of(outcome)["state"], "NO_ACTION")
        self.assertFalse(next(c for c in outcome["candidates"] if c["symbol"] == "ALPHA")["gates"]["quote"]["ok"])

    def test_liquidity_gate_uses_live_dollar_volume_and_falls_back_to_the_research_value(self):
        view = build_view(standard_pool())
        thin = run_decision(view, liquidity_fn=lambda s: {"median_dollar_volume_20d_usd": 1e6, "source": "live_daily_bars"})
        self.assertEqual(decision_of(thin)["state"], "NO_ACTION")
        alpha = next(c for c in thin["candidates"] if c["symbol"] == "ALPHA")
        self.assertIn("流动性", alpha["gate_summary"])
        fallback = run_decision(view, liquidity_fn=lambda s: None)
        self.assertEqual(decision_of(fallback)["state"], "RECOMMENDATION")
        self.assertEqual(decision_of(fallback)["gates"]["liquidity"]["source"], "research_snapshot")

    def test_price_below_three_dollars_fails_liquidity(self):
        view = build_view(standard_pool())
        market = fresh_market([e["symbol"] for e in view.shortlist], price=2.5)
        outcome = run_decision(view, market=market)
        self.assertEqual(decision_of(outcome)["state"], "NO_ACTION")

    def test_market_cap_above_50_billion_fails_liquidity_gate(self):
        view = build_view(standard_pool())
        market = fresh_market([e["symbol"] for e in view.shortlist], price=10.0)
        view.pool["ALPHA"]["shares_outstanding"] = 6e8                          # 10 美元 x 6 亿股 = 60 亿
        self.assertEqual(decision_of(run_decision(view, market=market))["state"], "NO_ACTION")


class VetoTests(unittest.TestCase):
    def veto_pool(self):
        """瓶颈 PASS(1.0) + 商业机会排序支持(0.3) = 1.3，但事件航图给了 FAILED（近 90 天增发）。"""
        b_link = sec_link("0000000021-26-000021", cik=21, supports="funded_demand", date="2026-08-10")
        c_link = sec_link("0000000022-26-000022", cik=21, supports="x", date="2026-08-05")
        f_link = sec_link("0000000023-26-000023", cik=21, supports="DILUTION_ATM", date="2026-09-15", summary="424B5：ATM")
        return {
            BOTTLENECK: [record("VETOED", "PASS", label="INVESTABLE", score=88.0, links=[b_link])] + filler("B", 20, base=30.0),
            COMMERCIAL: [record("VETOED", "ABSTAIN", score=95.0, links=[c_link])] + filler("C", 20, base=50.0),
            EVENT: [record("VETOED", "FAILED", label="DILUTION_VETO", score=0.0, links=[f_link], reasons=["稀释失效条件已触发：424B5：ATM"])] + filler("E", 20),
        }

    def test_an_event_atlas_dilution_failure_is_a_one_vote_veto_and_listed_as_a_conflict(self):
        view = build_view(self.veto_pool())
        summary = hub.support_summary(view, "VETOED", hub.branch_weights(None))
        self.assertTrue(summary["meets_threshold"])                             # 支持度够了，但被否决
        outcome = run_decision(view)
        decision = decision_of(outcome)
        self.assertEqual(decision["state"], "NO_ACTION")
        row = next(c for c in outcome["candidates"] if c["symbol"] == "VETOED")
        self.assertFalse(row["gates"]["veto"]["ok"])
        self.assertEqual(row["vetoes"][0]["id"], "EVENT_ATLAS_FAILED")
        self.assertTrue(row["vetoes"][0]["links"])                              # 否决理由带 SEC 原文
        self.assertEqual(decision["watchlist"][0]["failed_gate"], "一票否决")
        conflicts = hub.conflicts_for(view, "VETOED", row["vetoes"])
        self.assertEqual(conflicts[0]["kind"], "VETO")

    def test_insider_net_selling_and_bottleneck_kill_switch_also_veto(self):
        pool = self.veto_pool()
        pool[EVENT][0] = record("VETOED", "ABSTAIN", score=0.0, evidence={"insider_net_sell": True})
        self.assertEqual(hub.vetoes_for(build_view(pool), "VETOED")[0]["id"], "INSIDER_NET_SELL")
        pool = self.veto_pool()
        pool[EVENT][0] = record("VETOED", "ABSTAIN", score=0.0)
        pool[BOTTLENECK][0] = record("VETOED", "PASS", score=88.0, links=[sec_link("0000000021-26-000021", supports="x")],
                                     evidence={"hard_flags": {"kill_switch_triggered": True}})
        self.assertEqual(hub.vetoes_for(build_view(pool), "VETOED")[0]["id"], "BOTTLENECK_KILL_SWITCH")

    def test_other_branches_opposition_is_a_conflict_but_not_a_veto(self):
        pool = standard_pool()
        pool[BOTTLENECK][0] = record("ALPHA", "FAILED", label="BOTTLENECK_NOT_EQUITY", score=3.0, reasons=["GATE_C_CAPTURE_BELOW_MIN"])
        decision = decision_of(run_decision(build_view(pool)))
        self.assertEqual(decision["state"], "RECOMMENDATION")
        self.assertEqual(decision["conflicts"][0]["kind"], "OPPOSING_BRANCH")
        self.assertIn("瓶颈", decision["conflicts"][0]["text"])


class InvalidationTests(unittest.TestCase):
    def published(self, view=None):
        view = view or build_view(standard_pool(), fundamentals={"ALPHA": {
            "revenue_ttm": 1e8, "revenue_yoy": 0.10, "revenue_q_yoy": 0.12,
            "latest_periodic": {"form": "10-Q", "accession": "0000000002-26-000002", "filed": "2026-08-05", "period_end": "2026-06-30"}}})
        outcome = run_decision(view)
        self.assertEqual(decision_of(outcome)["state"], "RECOMMENDATION")
        return view, outcome

    def test_the_conditions_are_frozen_at_publication_and_reported(self):
        _view, outcome = self.published()
        invalidation = decision_of(outcome)["invalidation"]
        self.assertEqual(invalidation["status"], "ACTIVE")
        self.assertEqual(invalidation["status_text"], "生效中")
        ids = [c["id"] for c in invalidation["conditions"]]
        self.assertEqual(ids, ["DILUTION", "SUPPORT_REVOKED", "REVENUE_TURNS_NEGATIVE"])
        self.assertTrue(all(c["status"] == "OK" for c in invalidation["conditions"]))
        self.assertEqual(invalidation["not_monitored"][0]["id"], "INSIDER_SELL")     # 没数据的条件不假装能核对
        self.assertIn("10-Q", json.dumps(outcome["state"]["published"]["ALPHA"], ensure_ascii=False))     # 基线写死在记录里

    def test_frozen_record_survives_and_keeps_its_original_publication_time(self):
        view, first = self.published()
        later = run_decision(view, state=first["state"], now=NOW + timedelta(minutes=30))
        self.assertEqual(decision_of(later)["invalidation"]["published_at"], decision_of(first)["invalidation"]["published_at"])

    def test_new_dilution_after_publication_marks_it_invalidated_and_drops_the_recommendation(self):
        view, first = self.published()
        pool = standard_pool()
        pool[EVENT][0] = record("ALPHA", "FAILED", label="DILUTION_VETO", score=0.0,
                                links=[sec_link("0000000030-26-000030", cik=11, supports="DILUTION_ATM", summary="424B5：ATM")],
                                reasons=["稀释失效条件已触发：424B5：ATM"])
        changed = build_view(pool, fundamentals=view.fundamentals)
        second = run_decision(changed, state=first["state"], now=NOW + timedelta(minutes=5))
        decision = decision_of(second)
        self.assertNotEqual(decision.get("primary_symbol"), "ALPHA")
        record_ = second["state"]["published"]["ALPHA"]
        self.assertEqual(record_["status"], "INVALIDATED")
        self.assertEqual(record_["triggered"][0]["id"], "DILUTION")
        listed = decision["invalidated_recommendations"][0]
        self.assertEqual((listed["symbol"], listed["status_text"]), ("ALPHA", "已失效"))

    def test_an_invalidated_symbol_stays_out_even_if_its_scores_recover(self):
        view, first = self.published()
        pool = standard_pool()
        pool[EVENT][0] = record("ALPHA", "FAILED", label="DILUTION_VETO", score=0.0, links=[sec_link("0000000030-26-000030", cik=11)])
        second = run_decision(build_view(pool), state=first["state"], now=NOW + timedelta(minutes=5))
        third = run_decision(view, state=second["state"], now=NOW + timedelta(minutes=10))     # 分数恢复了
        self.assertNotEqual(decision_of(third).get("primary_symbol"), "ALPHA")
        row = next(c for c in third["candidates"] if c["symbol"] == "ALPHA")
        self.assertEqual(row["vetoes"][0]["id"], "PREVIOUSLY_INVALIDATED")

    def test_support_being_revoked_triggers_the_invalidation(self):
        view, first = self.published()
        revoked = build_view(standard_pool(), statuses={COMMERCIAL: "ABSTAIN"}, fundamentals=view.fundamentals)
        checks = hub.check_conditions(first["state"]["published"]["ALPHA"], revoked)
        self.assertEqual({c["id"]: c["status"] for c in checks}["SUPPORT_REVOKED"], "OK")      # 排序支持者整体 ABSTAIN 不算撤销
        pool = standard_pool()
        pool[EVENT][0] = record("ALPHA", "ABSTAIN", score=0.0)
        checks = hub.check_conditions(first["state"]["published"]["ALPHA"], build_view(pool, fundamentals=view.fundamentals))
        self.assertEqual({c["id"]: c["status"] for c in checks}["SUPPORT_REVOKED"], "TRIGGERED")

    def test_next_periodic_report_with_negative_revenue_growth_triggers(self):
        view, first = self.published()
        worse = deepcopy(view.fundamentals)
        worse["ALPHA"].update({"revenue_q_yoy": -0.04, "latest_periodic": {"form": "10-Q", "accession": "0000000099-26-000099", "filed": "2026-11-05", "period_end": "2026-09-30"}})
        checks = {c["id"]: c for c in hub.check_conditions(first["state"]["published"]["ALPHA"], build_view(standard_pool(), fundamentals=worse))}
        self.assertEqual(checks["REVENUE_TURNS_NEGATIVE"]["status"], "TRIGGERED")
        self.assertIn("-4.0%", checks["REVENUE_TURNS_NEGATIVE"]["detail"])

    def test_no_new_periodic_report_or_positive_growth_does_not_trigger(self):
        view, first = self.published()
        frozen = first["state"]["published"]["ALPHA"]
        self.assertEqual({c["id"]: c["status"] for c in hub.check_conditions(frozen, view)}["REVENUE_TURNS_NEGATIVE"], "OK")
        better = deepcopy(view.fundamentals)
        better["ALPHA"].update({"revenue_q_yoy": 0.03, "latest_periodic": {"form": "10-Q", "accession": "0000000099-26-000099", "filed": "2026-11-05", "period_end": "2026-09-30"}})
        checks = {c["id"]: c for c in hub.check_conditions(frozen, build_view(standard_pool(), fundamentals=better))}
        self.assertEqual(checks["REVENUE_TURNS_NEGATIVE"]["status"], "OK")

    def test_missing_fundamentals_are_reported_as_not_checkable_not_as_ok(self):
        view, first = self.published(build_view(standard_pool()))
        checks = {c["id"]: c["status"] for c in hub.check_conditions(first["state"]["published"]["ALPHA"], view)}
        self.assertEqual(checks["REVENUE_TURNS_NEGATIVE"], "NOT_CHECKABLE")

    def test_old_records_expire_after_sixty_days_and_are_republished_with_fresh_conditions(self):
        view, first = self.published()
        old_time = first["state"]["published"]["ALPHA"]["published_at"]
        later_view = build_view(standard_pool(), fundamentals=view.fundamentals, generated_at=NOW + timedelta(days=61) - timedelta(hours=1))
        later = run_decision(later_view, state=first["state"], now=NOW + timedelta(days=61))
        self.assertEqual(decision_of(later)["state"], "RECOMMENDATION")
        record_ = later["state"]["published"]["ALPHA"]
        self.assertEqual(record_["status"], "ACTIVE")
        self.assertNotEqual(record_["published_at"], old_time)              # 过期的那份被新的取代，不沿用旧条件


class SystemBlockedTests(unittest.TestCase):
    def test_research_snapshot_older_than_36_hours_blocks_with_a_plain_reason(self):
        view = build_view(standard_pool(), generated_at=NOW - timedelta(hours=37))
        decision = decision_of(run_decision(view))
        self.assertEqual(decision["state"], "SYSTEM_BLOCKED")
        self.assertEqual(decision["blocked_reason"], "RESEARCH_SNAPSHOT_STALE")
        self.assertIn("37", decision["message"])
        self.assertIn("36", decision["message"])
        self.assertIsNone(decision["action"])
        self.assertEqual(decision["action_code"], "SYSTEM_BLOCKED")

    def test_35_hours_is_still_fine_and_a_recent_research_check_keeps_an_unchanged_snapshot_fresh(self):
        self.assertEqual(decision_of(run_decision(build_view(standard_pool(), generated_at=NOW - timedelta(hours=35))))["state"], "RECOMMENDATION")
        weekend = build_view(standard_pool(), generated_at=NOW - timedelta(hours=60), checked_at=NOW - timedelta(hours=2))
        self.assertEqual(decision_of(run_decision(weekend))["state"], "RECOMMENDATION")

    def test_a_missing_receipt_or_failed_branch_blocks(self):
        view = build_view(standard_pool(), statuses={BOTTLENECK: "FAILED"}, problems=["BRANCH_FAILED:%s:boom" % BOTTLENECK])
        decision = decision_of(run_decision(view))
        self.assertEqual(decision["blocked_reason"], "RESEARCH_CHAIN_INCOMPLETE")
        self.assertIn("有分支运行失败", decision["message"])

    def test_all_market_data_down_blocks(self):
        decision = decision_of(run_decision(build_view(standard_pool()), quotes_available=False))
        self.assertEqual(decision["blocked_reason"], "MARKET_DATA_UNAVAILABLE")
        self.assertIn("行情源", decision["message"])

    def test_blocked_leaves_the_published_state_untouched(self):
        _view, first = InvalidationTests().published()
        blocked = run_decision(build_view(standard_pool(), generated_at=NOW - timedelta(hours=50)), state=first["state"])
        self.assertEqual(blocked["state"], first["state"])


class ActionCodeTests(unittest.TestCase):
    def test_every_state_has_a_machine_code(self):
        self.assertEqual(set(hub.ACTION_CODES), {"RECOMMENDATION", "NO_ACTION", "SYSTEM_BLOCKED"})
        with self.assertRaises(ValueError):
            hub.resolve_action_code("暴涨")


if __name__ == "__main__":
    unittest.main()
