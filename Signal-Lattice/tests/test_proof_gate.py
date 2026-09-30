"""B4.5 规则自证门：规则没在回测或前向成绩里证明自己有信息量，就不发布「研究跟进（看多）」。

覆盖：门关 -> NO_ACTION + 人话原因 + 观察名单 + 影子候选 + 影子记录；(a) 回测证据、(b) 前向证据各自能开门；
安慰剂更好不开；证据不足时收益数字不出现在任何公开响应里（反向断言）。
"""

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from signal_lattice import hub
from signal_lattice import ledger as L
from signal_lattice.ledger import Ledger
from signal_lattice.live_api import handler, public_report_view
from signal_lattice.live_config import LiveSettings
from signal_lattice.live_runtime import BENCHMARK_SYMBOL, LiveEngine, LiveStore
from hub_fixtures import (COMMERCIAL, EVENT, backtest_report, build_view, closed_proof, forward_stats, open_proof, run_decision, sec_link,
                          seed_shadow_evidence, standard_pool, write_research_dir, record, filler)
from test_live_engine import AFTER_CLOSE, SESSION, FakeGateway, make_bars, weekdays


def decision_of(outcome):
    return outcome["decision"]


class ProofGateRuleTests(unittest.TestCase):
    """规则本身：满足任一才开，回测里四条缺一不可。"""

    def test_the_backtest_leg_needs_every_condition(self):
        self.assertTrue(hub.proof_gate(backtest_report(), None)["open"])
        cases = {
            "窗口不足 6": backtest_report(windows=5),
            "相对 IWM 没有正超额": backtest_report(formal_iwm=-0.01),
            "相对 IWM 恰好为 0": backtest_report(formal_iwm=0.0),
            "没跑赢同档随机": backtest_report(formal_control=-0.001),
            "安慰剂更好": backtest_report(formal_iwm=0.02, placebo_iwm=0.03),
            "安慰剂与正式一样好": backtest_report(formal_iwm=0.02, placebo_iwm=0.02),
        }
        for name, report in cases.items():
            with self.subTest(name):
                gate = hub.proof_gate(report, None)
                self.assertFalse(gate["open"], name)
                self.assertEqual(gate["opened_by"], [])
                self.assertTrue(gate["headline"])

    def test_no_placebo_or_no_control_in_the_report_means_no_proof(self):
        report = backtest_report()
        del report["summary"]["placebo"]
        self.assertFalse(hub.proof_gate(report, None)["open"])
        report = backtest_report()
        report["summary"]["actual"]["pick_20"]["excess_vs_control"] = {"n": 0}
        self.assertFalse(hub.proof_gate(report, None)["open"])
        for junk in (None, {}, {"summary": 3}, "x", {"oos_windows": "abc", "summary": {"actual": {"pick_20": {}}}}):
            with self.subTest(junk=junk):
                self.assertFalse(hub.proof_gate(junk, None)["open"])

    def test_the_forward_leg_needs_eight_settled_a_55_percent_hit_rate_and_a_positive_mean(self):
        gate = hub.proof_gate(None, forward_stats(settled=8, hits=5, mean_excess=0.01))            # 62.5%
        self.assertTrue(gate["open"])
        self.assertEqual(gate["opened_by"], ["FORWARD"])
        cases = {
            "只有 7 条": forward_stats(settled=7, hits=7, mean_excess=0.05),
            "命中率 50%": forward_stats(settled=8, hits=4, mean_excess=0.05),
            "命中率 54.5%": forward_stats(settled=11, hits=6, mean_excess=0.05),
            "平均超额为 0": forward_stats(settled=10, hits=8, mean_excess=0.0),
            "平均超额为负": forward_stats(settled=10, hits=8, mean_excess=-0.01),
        }
        for name, stats in cases.items():
            with self.subTest(name):
                self.assertFalse(hub.proof_gate(None, stats)["open"], name)
        self.assertTrue(hub.proof_gate(None, forward_stats(settled=20, hits=11, mean_excess=0.001))["open"])     # 恰好 55%

    def test_either_leg_opens_the_gate_and_both_are_reported(self):
        both = hub.proof_gate(backtest_report(), forward_stats())
        self.assertEqual(both["opened_by"], ["BACKTEST", "FORWARD"])
        bad_backtest_good_forward = hub.proof_gate(backtest_report(formal_iwm=-0.04), forward_stats())
        self.assertEqual(bad_backtest_good_forward["opened_by"], ["FORWARD"])

    def test_forgetting_to_pass_the_gate_never_publishes(self):
        view = build_view(standard_pool())
        outcome = hub.decide(view, {e["symbol"]: {"price": 10.0, "quote_status": "FRESH"} for e in view.shortlist}, now=datetime(2026, 9, 30, 15, tzinfo=timezone.utc))
        self.assertEqual(outcome["decision"]["state"], "NO_ACTION")
        self.assertEqual(outcome["decision"]["proof_gate"]["state"], "CLOSED")

    def test_the_gate_is_the_same_pure_function_of_its_inputs(self):
        first = json.dumps(hub.proof_gate(backtest_report(formal_iwm=-0.03), forward_stats(settled=3)), sort_keys=True)
        second = json.dumps(hub.proof_gate(backtest_report(formal_iwm=-0.03), forward_stats(settled=3)), sort_keys=True)
        self.assertEqual(first, second)


class ClosedGateDecisionTests(unittest.TestCase):
    def outcome(self, proof=None, pool=None):
        return run_decision(build_view(pool or standard_pool()), proof=proof or closed_proof())

    def test_a_closed_gate_gives_no_action_with_the_plain_reason_instead_of_the_recommendation(self):
        decision = decision_of(self.outcome())
        self.assertEqual(decision["state"], "NO_ACTION")
        self.assertEqual(decision["action_code"], "NO_ACTION")
        self.assertIsNone(decision["action"])
        self.assertIsNone(decision["primary_symbol"])
        self.assertEqual(decision["no_action_cause"], "PROOF_GATE_CLOSED")
        self.assertEqual(decision["rationale"], "这套选股规则在过去 20 个月的回测里平均跑输小盘基准 IWM（20 日 −3.9%），在它证明自己之前不给建议。")
        self.assertNotIn("研究跟进（看多）", json.dumps({k: v for k, v in decision.items() if k not in ("proof_gate",)}, ensure_ascii=False).replace(hub.ACTION_FOLLOW + "）", ""))

    def test_the_watchlist_is_still_the_top_five_each_with_supporting_branches_the_gap_and_one_sec_link(self):
        pool = standard_pool()
        for i in range(8):
            pool[EVENT].append(record("P%d" % i, "PASS", score=50.0 - i, links=[sec_link("00000001%02d-26-000001" % i, cik=100 + i, date="2026-09-%02d" % (10 + i))]))
        decision = decision_of(self.outcome(pool=pool))
        watch = decision["watchlist"]
        self.assertEqual(len(watch), 5)
        self.assertEqual(watch[0]["symbol"], "ALPHA")                       # 「如果发布会选谁」排第一，也在名单里
        self.assertTrue(watch[0]["is_shadow_candidate"])
        self.assertEqual(watch[0]["failed_gate"], "规则自证门")
        for item in watch:
            self.assertTrue(item["sentence"].startswith("差在【"), item["sentence"])
            self.assertTrue(item["links"] and item["links"][0].startswith("https://www.sec.gov/"))
            self.assertIn("support_branches", item)
        self.assertEqual([b["label"] for b in watch[0]["support_branches"]], ["事件航图", "商业机会"])

    def test_the_shadow_candidate_is_who_would_have_been_published_and_why_it_is_not(self):
        outcome = self.outcome()
        shadow = decision_of(outcome)["shadow_candidate"]
        self.assertEqual(shadow["symbol"], "ALPHA")
        self.assertIn("今天如果发布，会是 ALPHA", shadow["sentence"])
        self.assertIn("规则自证门没开", shadow["why_not_published"])
        self.assertTrue(shadow["sources"])
        self.assertEqual(shadow["support_total"], 1.3)
        # 同样输入、门开着 -> 发布的就是这一只：影子候选不是另一套规则
        self.assertEqual(decision_of(run_decision(build_view(standard_pool()), proof=open_proof()))["primary_symbol"], shadow["symbol"])

    def test_when_nothing_would_have_been_published_there_is_no_shadow_candidate_and_it_says_so(self):
        decision = decision_of(run_decision(build_view(standard_pool(), statuses={COMMERCIAL: "ABSTAIN"}), proof=closed_proof()))
        self.assertEqual(decision["state"], "NO_ACTION")
        self.assertIsNone(decision["shadow_candidate"])
        self.assertIn("没有影子候选", decision["shadow_note"])
        self.assertTrue(decision["watchlist"])

    def test_candidates_carry_the_sixth_gate_and_the_gap_names_it(self):
        outcome = self.outcome()
        alpha = next(c for c in outcome["candidates"] if c["symbol"] == "ALPHA")
        self.assertFalse(alpha["gates"]["proof"]["ok"])
        self.assertTrue(alpha["passes_candidate_gates"])
        self.assertFalse(alpha["passes_all_gates"])
        self.assertIn("规则自证门", alpha["gate_summary"])
        self.assertEqual(alpha["branch_kinds"][EVENT], "PASS")
        self.assertEqual(decision_of(outcome)["qualifying_candidates"], 1)

    def test_an_open_gate_changes_nothing_about_the_per_stock_rule(self):
        opened = run_decision(build_view(standard_pool()), proof=open_proof())
        self.assertEqual(decision_of(opened)["state"], "RECOMMENDATION")
        self.assertEqual(decision_of(opened)["proof_gate"]["opened_by"], ["BACKTEST"])
        self.assertTrue(next(c for c in opened["candidates"] if c["symbol"] == "ALPHA")["gates"]["proof"]["ok"])

    def test_a_closed_gate_publishes_nothing_and_freezes_no_conditions(self):
        outcome = self.outcome()
        self.assertEqual(outcome["state"].get("published", {}), {})

    def test_system_blocked_beats_the_gate(self):
        view = build_view(standard_pool(), generated_at=datetime(2026, 9, 30, 15, tzinfo=timezone.utc) - timedelta(hours=40))
        self.assertEqual(decision_of(run_decision(view, proof=closed_proof()))["state"], "SYSTEM_BLOCKED")

    def test_each_failed_check_is_named_in_the_headline(self):
        control = hub.proof_gate(backtest_report(formal_iwm=0.02, formal_control=-0.01, placebo_iwm=-0.02), None)
        self.assertIn("没有跑赢同市值档的随机抽样", control["headline"])
        placebo = hub.proof_gate(backtest_report(formal_iwm=0.02, formal_control=0.01, placebo_iwm=0.03), None)
        self.assertIn("安慰剂", placebo["headline"])
        self.assertIn("+3.0%", placebo["headline"])
        few = hub.proof_gate(backtest_report(windows=4), None)
        self.assertIn("只有 4 个样本外月份", few["headline"])
        self.assertIn("样本外窗口 4/6", few["line"])
        none = hub.proof_gate(None, None)
        self.assertIn("还没有可用的回测", none["headline"])


class NoNumbersWithoutEvidenceTests(unittest.TestCase):
    """反向断言：证据不足的那一半，收益数字在门的判定里根本不存在，公开响应里当然也没有。"""

    THIN_BACKTEST = backtest_report(windows=4, formal_iwm=-0.07771, formal_control=-0.06662, placebo_iwm=0.05551, hit_rate=0.41273)
    THIN_FORWARD = forward_stats(settled=3, hits=1, mean_excess=-0.04444)
    NUMBERS = ("0.07771", "7.8%", "0.06662", "6.7%", "0.05551", "5.6%", "0.41273", "0.04444", "4.4%")

    def test_the_gate_object_itself_has_no_numbers_when_evidence_is_insufficient(self):
        gate = hub.proof_gate(self.THIN_BACKTEST, self.THIN_FORWARD)
        text = json.dumps(gate, ensure_ascii=False)
        for number in self.NUMBERS:
            self.assertNotIn(number, text)
        self.assertNotIn("formal_20d_vs_iwm", gate["backtest"])
        self.assertNotIn("hit_rate", gate["forward"])
        self.assertIsNone(gate["backtest"]["checks"]["beats_iwm"])           # 没评估，不是「假」

    def test_sufficient_evidence_does_publish_its_numbers_including_the_bad_ones(self):
        gate = hub.proof_gate(backtest_report(windows=20, formal_iwm=-0.0393, formal_control=-0.0319, placebo_iwm=0.0238), None)
        self.assertEqual(gate["backtest"]["formal_20d_vs_iwm"], -0.0393)
        self.assertEqual(gate["backtest"]["placebo_20d_vs_iwm"], 0.0238)
        self.assertIn("−3.9%", gate["line"])
        self.assertIn("+2.4%", gate["line"])

    def test_the_public_view_strips_numbers_even_if_a_private_report_smuggled_them_in(self):
        smuggled = hub.proof_gate(backtest_report(), forward_stats())
        smuggled["backtest"]["sufficient"] = False
        smuggled["forward"]["sufficient"] = False
        report = {"state": "DATA_READY", "proof_gate": smuggled, "decision": {"state": "NO_ACTION", "proof_gate": smuggled},
                  "ledger": {"sample_status": "SAMPLE_INSUFFICIENT", "settled": {"20": 2, "60": 0}, "horizons": {}, "recent": [],
                             "shadow": {"sample_status": "SAMPLE_INSUFFICIENT", "settled": {"20": 2, "60": 0}, "message": "样本不足，暂不下结论",
                                        "horizons": {"20": {"settled": 2, "status": "SAMPLE_INSUFFICIENT", "hit_rate": 0.987654, "mean_excess_vs_iwm": 0.123456}},
                                        "recent": [{"trading_day": "2026-10-01", "symbol": "ALPHA", "excess_vs_iwm_20": 0.777777}]}}}
        text = json.dumps(public_report_view(report), ensure_ascii=False)
        self.assertNotIn("formal_20d_vs_iwm", text)
        self.assertNotIn("placebo_20d_vs_iwm", text)
        self.assertNotIn("mean_excess_vs_iwm", text)
        self.assertNotIn("0.987654", text)
        self.assertNotIn("0.123456", text)
        self.assertNotIn("0.777777", text)


class ShadowLedgerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ledger = Ledger(Path(self._tmp.name) / "ledger.sqlite")
        self.addCleanup(self.ledger.close)
        days, d = [], datetime.fromisoformat("2026-09-01")
        while len(days) < 90:
            if d.weekday() < 5:
                days.append(d.date().isoformat())
            d += timedelta(days=1)
        self.days = days
        price = lambda start, daily: [(day, start * (1 + daily) ** i) for i, day in enumerate(days)]
        self.iwm = price(200.0, 0.001)
        self.book = {"ALPHA": price(10.0, 0.004), "CTRL": price(20.0, 0.002)}

    def decision(self, symbol="ALPHA"):
        proof = closed_proof()
        return {"state": "NO_ACTION", "action": None, "action_code": "NO_ACTION", "watchlist": [], "proof_gate": proof,
                "data_chain": {"snapshot_sha256": "a" * 64},
                "shadow_candidate": {"symbol": symbol, "name": symbol + " Inc", "market_cap_usd": 1.2e9, "price": 10.0, "support_total": 1.3,
                                     "support_branches": [{"branch_id": EVENT, "kind": "PASS", "weighted": 1.0}], "reasons": [], "sources": [], "sentence": "x"}}

    def test_a_shadow_row_is_recorded_once_per_day_and_kept_apart_from_the_formal_record(self):
        day = self.days[5]
        self.assertTrue(self.ledger.record_shadow(day, self.decision(), close_price=dict(self.book["ALPHA"])[day], iwm_close=dict(self.iwm)[day]))
        self.assertFalse(self.ledger.record_shadow(day, self.decision("BETA"), close_price=9.0, iwm_close=1.0))       # 第一条为准
        self.assertEqual(self.ledger.db.execute("SELECT symbol FROM shadow_record").fetchall()[0][0], "ALPHA")
        self.assertEqual(self.ledger.db.execute("SELECT COUNT(*) FROM daily_record").fetchone()[0], 0)
        self.assertEqual(self.ledger.branch_hit_stats(20), {})                                                          # 不进分支权重

    def test_a_shadow_needs_a_close_price_and_a_no_action_decision(self):
        with self.assertRaises(ValueError):
            self.ledger.record_shadow(self.days[5], self.decision(), close_price=None, iwm_close=1.0)
        with self.assertRaises(ValueError):
            self.ledger.record_shadow(self.days[5], {"state": "RECOMMENDATION"}, close_price=1.0, iwm_close=1.0)

    def test_shadow_tables_are_append_only_too(self):
        day = self.days[5]
        self.ledger.record_shadow(day, self.decision(), close_price=10.0, iwm_close=200.0)
        self.ledger.settle_shadow_due(self.book.get, self.iwm, datetime(2026, 12, 1, tzinfo=timezone.utc))
        for statement in ("UPDATE shadow_record SET close_price = 1", "DELETE FROM shadow_record", "UPDATE shadow_settlement SET hit = 0", "DELETE FROM shadow_settlement"):
            with self.subTest(statement), self.assertRaises(Exception):
                self.ledger.db.execute(statement)

    def test_shadow_settles_at_20_and_60_days_with_the_random_control(self):
        day = self.days[5]
        self.ledger.record_shadow(day, self.decision(), close_price=dict(self.book["ALPHA"])[day], iwm_close=dict(self.iwm)[day],
                                  control={"symbol": "CTRL", "tier": "10-20亿美元", "seed": "s", "pool_size": 3, "pool_sha": "p"},
                                  control_close=dict(self.book["CTRL"])[day])
        early = self.ledger.settle_shadow_due(self.book.get, self.iwm[: 5 + 21], datetime(2026, 10, 1, tzinfo=timezone.utc))
        self.assertEqual([(d["horizon"], d["kind"]) for d in early], [(20, "shadow")])
        row = self.ledger.db.execute("SELECT * FROM shadow_settlement WHERE horizon = 20").fetchone()
        self.assertEqual(row["hit"], 1)
        self.assertIsNotNone(row["excess_vs_control"])
        self.assertEqual(self.ledger.settle_shadow_due(self.book.get, self.iwm[: 5 + 21], datetime(2026, 10, 1, tzinfo=timezone.utc)), [])       # 幂等
        later = self.ledger.settle_shadow_due(self.book.get, self.iwm, datetime(2026, 12, 1, tzinfo=timezone.utc))
        self.assertEqual([d["horizon"] for d in later], [60])
        self.assertEqual(self.ledger.db.execute("SELECT COUNT(*) FROM settlement").fetchone()[0], 0)

    def test_forward_evidence_counts_shadow_and_formal_together(self):
        seed_shadow_evidence(Path(self._tmp.name) / "ledger.sqlite", settled=0)
        seed = L.Ledger(Path(self._tmp.name) / "seed.sqlite")
        self.addCleanup(seed.close)
        self.assertEqual(seed.forward_evidence(20), {"shadow_settled": 0, "formal_settled": 0, "hits": 0, "settled": 0, "mean_excess": None})

    def test_below_eight_settled_shadow_rows_the_public_summary_has_no_numbers_and_at_eight_it_has_all_of_them(self):
        path = Path(self._tmp.name) / "seeded.sqlite"
        seed_shadow_evidence(path, settled=7, hits=6, excess=0.0123456)
        ledger = Ledger(path)
        self.addCleanup(ledger.close)
        thin = ledger.shadow_summary()
        text = json.dumps(thin, ensure_ascii=False)
        self.assertEqual(thin["sample_status"], "SAMPLE_INSUFFICIENT")
        self.assertIn("样本不足，暂不下结论", thin["message"])
        for banned in ("hit_rate", "0.0123", "excess_vs_iwm_20", "mean_excess"):
            self.assertNotIn(banned, text)
        path2 = Path(self._tmp.name) / "seeded8.sqlite"
        seed_shadow_evidence(path2, settled=8, hits=3, excess=0.0123456)
        full = Ledger(path2)
        self.addCleanup(full.close)
        enough = full.shadow_summary()["horizons"]["20"]
        self.assertEqual(enough["status"], "SUFFICIENT")
        self.assertAlmostEqual(enough["hit_rate"], 3 / 8)
        self.assertAlmostEqual(enough["mean_excess_vs_iwm"], (3 * 0.0123456 - 5 * 0.0123456) / 8)     # 亏损也在里面
        self.assertIn("shadow", full.summary())


class EngineEndToEndTests(unittest.TestCase):
    """实时层：门关 -> 影子记录；门开 -> 建议。网络一律替身。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.research = self.root / "research"
        write_research_dir(self.research, standard_pool())
        base = LiveSettings.from_env(Path(__file__).resolve().parents[1])
        self.settings = replace(base, state_dir=self.root / "state", research_dir=self.research, backtest_dir=self.root / "bt")

    def engine(self, gateway):
        engine = LiveEngine(self.settings)
        engine.gateway = gateway
        return engine

    def write_backtest(self, **kwargs):
        (self.root / "bt").mkdir(exist_ok=True)
        (self.root / "bt" / "hub-backtest.json").write_text(json.dumps(backtest_report(**kwargs)), "utf-8")

    def bars(self, end="2026-09-30", n=40):
        days = weekdays(end, n)
        symbols = ("ALPHA", "BETA", BENCHMARK_SYMBOL, *[f"E{i:02d}" for i in range(20)], *[f"C{i:02d}" for i in range(20)], *[f"B{i:02d}" for i in range(20)])
        return days, {s: make_bars(s, days, daily=0.004, volume=5_000_000.0) for s in symbols}

    def test_with_no_backtest_and_no_forward_record_the_live_round_says_no_action_and_names_the_shadow_candidate(self):
        report = self.engine(FakeGateway(SESSION)).run_once(SESSION)
        decision = report["decision"]
        self.assertEqual(report["state"], "DATA_READY")
        self.assertEqual((decision["state"], decision["no_action_cause"]), ("NO_ACTION", "PROOF_GATE_CLOSED"))
        self.assertEqual(decision["shadow_candidate"]["symbol"], "ALPHA")
        self.assertEqual(report["proof_gate"]["state"], "CLOSED")
        self.assertEqual(report["proof_gate"], decision["proof_gate"])
        self.assertTrue(decision["watchlist"])
        self.assertEqual(self.engine(FakeGateway(SESSION)).store.hub_state().get("published", {}), {})     # 没有发布，也就没有冻结失效条件

    def test_after_the_close_the_shadow_candidate_is_recorded_once_next_to_the_formal_no_action_row(self):
        days, bars = self.bars()
        engine = self.engine(FakeGateway(AFTER_CLOSE, bars=bars))
        report = engine.run_once(AFTER_CLOSE)
        self.assertEqual(report["ledger"]["recorded_days"], 1)
        self.assertEqual(report["ledger"]["recommendation_days"], 0)
        self.assertEqual(report["ledger"]["shadow"]["recorded_days"], 1)
        self.assertEqual(report["ledger"]["last_run"]["shadow_recorded"], True)
        again = engine.run_once(AFTER_CLOSE + timedelta(minutes=1))
        self.assertEqual(again["ledger"]["shadow"]["recorded_days"], 1)                     # 同一天不重复记
        ledger = Ledger(self.settings.state_dir / "ledger.sqlite")
        try:
            row = ledger.db.execute("SELECT * FROM shadow_record").fetchone()
            self.assertEqual((row["trading_day"], row["symbol"]), ("2026-09-30", "ALPHA"))
            self.assertAlmostEqual(row["close_price"], bars["ALPHA"][-1].close)
            self.assertIsNotNone(row["control_symbol"])
            self.assertEqual(ledger.db.execute("SELECT decision_state FROM daily_record").fetchone()[0], "NO_ACTION")
        finally:
            ledger.close()

    def test_the_shadow_candidate_settles_after_twenty_trading_days_and_the_public_summary_stays_silent_below_eight(self):
        days, bars = self.bars(n=60)
        self.engine(FakeGateway(AFTER_CLOSE, bars=bars)).run_once(AFTER_CLOSE)
        later_days = weekdays("2026-11-04", 60)
        later_bars = {s: make_bars(s, later_days, daily=0.004, volume=5_000_000.0) for s in bars}
        write_research_dir(self.research, standard_pool(), generated_at=datetime(2026, 11, 4, 19, tzinfo=timezone.utc))
        later = datetime(2026, 11, 4, 21, tzinfo=timezone.utc)
        report = self.engine(FakeGateway(later, bars=later_bars)).run_once(later)
        shadow = report["ledger"]["shadow"]
        self.assertEqual(shadow["settled"]["20"], 1)
        self.assertEqual(shadow["sample_status"], "SAMPLE_INSUFFICIENT")
        self.assertNotIn("hit_rate", json.dumps(shadow))
        self.assertEqual(report["contribution_weights"]["weight_sample_count"], 0)           # 影子结算不进分支权重

    def test_a_passing_backtest_opens_the_gate_and_the_recommendation_is_published(self):
        self.write_backtest()
        report = self.engine(FakeGateway(SESSION)).run_once(SESSION)
        self.assertEqual(report["decision"]["state"], "RECOMMENDATION")
        self.assertEqual(report["decision"]["primary_symbol"], "ALPHA")
        self.assertEqual(report["proof_gate"]["opened_by"], ["BACKTEST"])

    def test_a_backtest_where_the_placebo_is_better_keeps_the_gate_shut(self):
        self.write_backtest(formal_iwm=0.02, formal_control=0.02, placebo_iwm=0.05)
        report = self.engine(FakeGateway(SESSION)).run_once(SESSION)
        self.assertEqual(report["decision"]["state"], "NO_ACTION")
        self.assertIn("安慰剂", report["decision"]["rationale"])

    def test_eight_settled_shadow_candidates_with_a_good_record_open_the_gate_without_any_backtest(self):
        seed_shadow_evidence(self.settings.state_dir / "ledger.sqlite", settled=8, hits=5)
        report = self.engine(FakeGateway(SESSION)).run_once(SESSION)
        self.assertEqual(report["decision"]["state"], "RECOMMENDATION")
        self.assertEqual(report["proof_gate"]["opened_by"], ["FORWARD"])
        self.assertEqual(report["backtest"]["status"], "NOT_RUN")

    def test_the_public_response_has_no_return_numbers_from_an_insufficient_backtest_or_forward_record(self):
        self.write_backtest(windows=4, formal_iwm=-0.07771, formal_control=-0.06662, placebo_iwm=0.05551, hit_rate=0.41273)
        seed_shadow_evidence(self.settings.state_dir / "ledger.sqlite", settled=3, hits=1, excess=0.04444)
        engine = self.engine(FakeGateway(SESSION))
        engine.run_once(SESSION)
        engine.store.write_heartbeat(datetime.now(timezone.utc))
        stored = engine.store.latest()
        stored["generated_at"] = datetime.now(timezone.utc).isoformat()
        engine.store.save(stored)
        request_handler = handler(self.settings, engine.store)
        from test_live_api import LiveApiTests
        getter = LiveApiTests()._get_without_tcp
        for path in ("/api/v1/report/latest", "/api/v1/whitebox/summary", "/api/v1/whitebox/skills", "/api/v1/whitebox/backtest/latest"):
            with self.subTest(path=path):
                _status, payload = getter(request_handler, path)
                text = json.dumps(payload, ensure_ascii=False)
                for number in NoNumbersWithoutEvidenceTests.NUMBERS + ("0.04444",):
                    self.assertNotIn(number, text)
        _status, report = getter(request_handler, "/api/v1/report/latest")
        self.assertEqual(report["proof_gate"]["backtest"]["windows"], 4)
        self.assertEqual(report["proof_gate"]["forward"]["settled"], 3)
        self.assertEqual(report["decision"]["state"], "NO_ACTION")


if __name__ == "__main__":
    unittest.main()
