"""事件航图分支：参数校验、事件状态、PASS/ABSTAIN/FAILED 规则、稀释失效风险、as_of 时点。"""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from _event_fixtures import add_buy, add_p_history

from signal_lattice.branches import event_atlas as atlas
from signal_lattice.evidence.eventstore import EventStore

PARAMS = atlas.load_params()
ENTRY = {"symbol": "TEST", "cik": 1234567, "name": "Test Corp", "market_cap_usd": 800_000_000.0, "exchange": "Nasdaq"}
OWNER = 900001


def base_store():
    store = EventStore(":memory:")
    store.touch_owner_first([(OWNER, "2012-01-01")], "test")
    store.commit()
    return store


def add_filing(store, form, accession, filed, cik=1234567):
    store.db.execute("INSERT INTO filings (cik, accession, form, filed, company) VALUES (?,?,?,?,?)",
                     (cik, accession, form, filed, "Test Corp"))
    store.commit()


def add_meta(store, accession, form, filed, items=None, primary="doc.htm", cik=1234567, accepted=None):
    store.db.execute("INSERT INTO filing_meta (accession, cik, form, filed, accepted_at, report_date, items, primary_document) "
                     "VALUES (?,?,?,?,?,?,?,?)", (accession, cik, form, filed, accepted, filed, items, primary))
    store.commit()


def evaluate(store, as_of="2026-09-29", study=None):
    events = atlas.build_events(store, [ENTRY], as_of, PARAMS, since="2024-10-01")
    return atlas.evaluate_company(ENTRY, events, store, as_of, PARAMS, study or {}), events


class ParamsTests(unittest.TestCase):
    def test_shipped_params_are_valid(self):
        self.assertEqual(PARAMS["schema"], "equity-event-atlas/params-v1")
        self.assertEqual(PARAMS["insider"]["min_purchase_usd"], 25000)
        self.assertEqual(PARAMS["study"]["min_sample"], 30)

    def test_bad_params_are_rejected(self):
        def bad(mutate):
            params = copy.deepcopy(dict(PARAMS))
            mutate(params)
            with self.assertRaises(atlas.ParamsError):
                atlas.validate_params(params)
        bad(lambda p: p.update(schema="other"))
        bad(lambda p: p["insider"].pop("window_days"))
        bad(lambda p: p["insider"].update(min_purchase_usd=-1))
        bad(lambda p: p["insider"].update(routine_history_years=2))
        bad(lambda p: p["study"].update(min_sample=1))
        bad(lambda p: p["study"].update(entry_lag_trading_days=0))
        bad(lambda p: p["study"].update(horizons_trading_days=[]))
        bad(lambda p: p["study"].update(medium_confidence_sample=10))
        bad(lambda p: p["dilution"].update(share_growth_yoy_threshold=0.9))
        bad(lambda p: p["verdict"].update(positive_kinds=["NOT_A_KIND"]))
        bad(lambda p: p.pop("verdict"))

    def test_unreadable_file_is_a_params_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "params.json"
            path.write_text("{not json")
            with self.assertRaises(atlas.ParamsError):
                atlas.load_params(path)
            path.write_text(json.dumps(dict(PARAMS)))
            self.assertEqual(atlas.load_params(path)["params_version"], PARAMS["params_version"])


class EventStateTests(unittest.TestCase):
    def test_opportunistic_buy_event_has_family_state_mechanism_and_times(self):
        store = base_store()
        add_buy(store, "0001234567-26-000001", OWNER, filed="2026-08-12", first_trade="2026-08-10", amount=120_000)
        events = atlas.build_events(store, [ENTRY], "2026-09-29", PARAMS)
        event = next(e for e in events if e.kind == "INSIDER_BUY_OPPORTUNISTIC")
        self.assertEqual((event.family, event.state), ("INSIDER_OWNERSHIP", "COMPLETED"))
        self.assertIn("EXPECTATIONS", event.mechanisms)
        self.assertEqual((event.effective_at, event.published_date), ("2026-08-10", "2026-08-12"))
        self.assertTrue(event.published_at.startswith("2026-08-12"))
        self.assertTrue(event.source_url.startswith("https://www.sec.gov/Archives/edgar/data/1234567/"))
        self.assertTrue(event.source_url.endswith("-index.htm"))

    def test_shelf_is_conditional_and_prospectus_is_confirmed(self):
        store = base_store()
        add_filing(store, "S-3", "0001234567-26-000010", "2026-07-01")
        add_filing(store, "424B5", "0001234567-26-000011", "2026-07-02")
        store.db.execute("INSERT INTO prospectus_class VALUES ('0001234567-26-000011','ATM','now')")
        store.commit()
        events = {e.kind: e for e in atlas.build_events(store, [ENTRY], "2026-09-29", PARAMS)}
        self.assertEqual(events["DILUTION_SHELF"].state, "CONDITIONAL")
        self.assertEqual(events["DILUTION_ATM"].state, "CONFIRMED")
        self.assertEqual(events["DILUTION_ATM"].family, "FINANCING_DILUTION")

    def test_debt_prospectus_is_not_dilution(self):
        store = base_store()
        add_filing(store, "424B5", "0001234567-26-000011", "2026-07-02")
        store.db.execute("INSERT INTO prospectus_class VALUES ('0001234567-26-000011','OTHER_PROSPECTUS','now')")
        store.commit()
        verdict, events = evaluate(store)
        self.assertEqual([e.kind for e in events], ["PROSPECTUS_OTHER"])
        self.assertEqual(verdict["verdict"], "ABSTAIN")

    def test_eight_k_items_map_to_families(self):
        store = base_store()
        add_meta(store, "0001234567-26-000020", "8-K", "2026-08-01", items="1.01,9.01", accepted="2026-08-01T20:30:00.000Z")
        add_meta(store, "0001234567-26-000021", "8-K", "2026-08-05", items="2.02,9.01")
        add_meta(store, "0001234567-26-000022", "8-K", "2026-08-06", items="5.02")
        add_meta(store, "0001234567-26-000023", "8-K", "2026-08-07", items="7.01")
        kinds = {e.kind: e for e in atlas.build_events(store, [ENTRY], "2026-09-29", PARAMS)}
        self.assertEqual(set(kinds), {"MATERIAL_AGREEMENT", "EARNINGS_RESULTS", "EXEC_CHANGE"})
        self.assertEqual(kinds["EARNINGS_RESULTS"].family, "EARNINGS_GUIDANCE")
        self.assertEqual(kinds["MATERIAL_AGREEMENT"].published_at, "2026-08-01T20:30:00.000Z")
        self.assertIn("document_url", kinds["MATERIAL_AGREEMENT"].details)

    def test_13d_is_ownership_family(self):
        store = base_store()
        add_filing(store, "SCHEDULE 13D", "0000555000-26-000004", "2026-09-01")
        event = atlas.build_events(store, [ENTRY], "2026-09-29", PARAMS)[0]
        self.assertEqual((event.kind, event.family), ("ACTIVIST_13D", "INSIDER_OWNERSHIP"))

    def test_share_growth_needs_threshold_and_split_is_not_dilution(self):
        store = base_store()
        add_filing(store, "10-Q", "Q-NEW", "2026-08-05")
        add_filing(store, "10-Q", "Q-OLD", "2025-08-05")
        add_filing(store, "10-Q", "Q-JUMP", "2026-05-05")
        store.add_shares([(1234567, "2025-08-01", 100e6, "Q-OLD"), (1234567, "2026-08-01", 125e6, "Q-NEW"),
                          (1234567, "2026-05-01", 300e6, "Q-JUMP"), (1234567, "2025-05-01", 100e6, "Q-OLD2")])
        kinds = [e.kind for e in atlas.build_events(store, [ENTRY], "2026-09-29", PARAMS)]
        self.assertIn("SHARE_COUNT_GROWTH", kinds)            # +25%
        self.assertIn("SHARE_COUNT_JUMP_UNEXPLAINED", kinds)  # +200%：疑似拆股，不算稀释


class VerdictTests(unittest.TestCase):
    def with_buy(self, **kwargs):
        store = base_store()
        add_buy(store, "0001234567-26-000001", OWNER, filed=kwargs.get("filed", "2026-08-12"), first_trade="2026-08-10",
                amount=kwargs.get("amount", 120_000), role=kwargs.get("role", "CEO"))
        return store

    def test_pass_needs_opportunistic_buy_and_carries_sec_link(self):
        verdict, _ = evaluate(self.with_buy())
        self.assertEqual(verdict["verdict"], "PASS")
        self.assertGreaterEqual(len(verdict["evidence"]), 1)
        self.assertTrue(all(item["url"].startswith("https://www.sec.gov/Archives/edgar/data/") for item in verdict["evidence"]))
        self.assertGreater(verdict["score"], 0)
        self.assertEqual(verdict["invalidation_risk"], [])
        self.assertTrue(verdict["invalidation_conditions"])

    def test_no_events_abstains(self):
        verdict, _ = evaluate(base_store())
        self.assertEqual((verdict["verdict"], verdict["score"]), ("ABSTAIN", 0))

    def test_routine_buyer_alone_abstains(self):
        store = self.with_buy()
        add_p_history(store, OWNER, [(2023, 8), (2024, 8), (2025, 8)])
        verdict, _ = evaluate(store)
        self.assertEqual(verdict["verdict"], "ABSTAIN")
        self.assertEqual(verdict["insider_window"]["counts"]["routine"], 1)

    def test_plan_and_small_and_unknown_history_do_not_pass(self):
        store = base_store()
        add_buy(store, "P-1", OWNER, amount=200_000, plan=1)
        add_buy(store, "P-2", OWNER, amount=10_000)
        add_buy(store, "P-3", 900009, amount=200_000)   # 内部人首次出现日未知 -> 无法分类
        verdict, _ = evaluate(store)
        self.assertEqual(verdict["verdict"], "ABSTAIN")

    def test_recent_offering_overrides_positive_and_is_flagged(self):
        store = self.with_buy()
        add_filing(store, "424B5", "0001234567-26-000030", "2026-08-20")
        verdict, _ = evaluate(store)
        self.assertEqual(verdict["verdict"], "FAILED")
        self.assertIn("DILUTION_OFFERING", verdict["invalidation_risk"])
        self.assertIn("被稀释否决", verdict["reason"])

    def test_atm_in_last_90_days_is_flagged_even_without_positive_event(self):
        store = base_store()
        add_filing(store, "424B5", "0001234567-26-000030", "2026-08-20")
        store.db.execute("INSERT INTO prospectus_class VALUES ('0001234567-26-000030','ATM','now')")
        store.commit()
        verdict, _ = evaluate(store)
        self.assertEqual(verdict["verdict"], "FAILED")
        self.assertIn("DILUTION_ATM", verdict["invalidation_risk"])

    def test_old_offering_outside_90_days_does_not_fail(self):
        store = self.with_buy()
        add_filing(store, "424B5", "0001234567-26-000030", "2026-05-01")
        verdict, _ = evaluate(store)
        self.assertEqual(verdict["verdict"], "PASS")

    def test_shelf_only_keeps_pass_but_flags_invalidation_risk(self):
        store = self.with_buy()
        add_filing(store, "S-3", "0001234567-26-000031", "2026-09-10")
        verdict, _ = evaluate(store)
        self.assertEqual(verdict["verdict"], "PASS")
        self.assertEqual(verdict["invalidation_risk"], ["DILUTION_SHELF"])

    def test_share_count_growth_fails(self):
        store = self.with_buy()
        add_filing(store, "10-Q", "Q-NEW", "2026-08-05")
        add_filing(store, "10-Q", "Q-OLD", "2025-08-05")
        store.add_shares([(1234567, "2025-08-01", 100e6, "Q-OLD"), (1234567, "2026-08-01", 120e6, "Q-NEW")])
        verdict, _ = evaluate(store)
        self.assertEqual(verdict["verdict"], "FAILED")

    def test_as_of_hides_later_filings(self):
        store = self.with_buy(filed="2026-08-12")
        add_filing(store, "424B5", "0001234567-26-000030", "2026-09-20")
        early, _ = evaluate(store, as_of="2026-09-01")
        late, _ = evaluate(store, as_of="2026-09-29")
        self.assertEqual(early["verdict"], "PASS")     # 增发是 09-20 才申报的，09-01 看不到
        self.assertEqual(late["verdict"], "FAILED")
        before_buy, events = evaluate(store, as_of="2026-08-11")
        self.assertEqual(before_buy["verdict"], "ABSTAIN")
        self.assertEqual(events, [])

    def test_senior_buyer_and_size_raise_the_score(self):
        ceo, _ = evaluate(self.with_buy(role="Chief Executive Officer", amount=400_000))
        other, _ = evaluate(self.with_buy(role="Director", amount=40_000))
        self.assertGreater(ceo["score"], other["score"])

    def test_baseline_is_attached_from_study(self):
        stats = {"INSIDER_BUY_OPPORTUNISTIC": {"n_events": 3, "n_after_dedupe": 3,
                                               "horizons": {"20": {"n": 3, "status": "样本不足"}}}}
        verdict, _ = evaluate(self.with_buy(), study=stats)
        self.assertEqual(verdict["baseline"]["INSIDER_BUY_OPPORTUNISTIC"]["horizons"]["20"]["status"], "样本不足")


if __name__ == "__main__":
    unittest.main()
