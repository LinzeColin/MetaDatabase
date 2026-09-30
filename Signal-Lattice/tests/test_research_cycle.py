"""研究层管线（合成数据、真实子进程）：五个分支都真实参与、收据里 snapshot_hash 相同、每个 PASS 带 SEC 链接、
shortlist 规则、同一快照重复运行不重复计数、强制重跑结果逐字节一致。"""

from __future__ import annotations

import json
import os
import random
import shutil
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import branch_fixtures as fx
import signal_lattice
from signal_lattice import research_cycle as RC
from signal_lattice.branch_runner import BranchReceipt
from signal_lattice.evidence.eventstore import EventStore
from signal_lattice.evidence.factstore import FactStore
from signal_lattice.evidence.history_prices import BarStore
from signal_lattice.evidence.structure_text import EXTRACTOR_VERSION, Extraction, FilingExtraction
from signal_lattice.marketdata.models import Bar

ROOT = Path(signal_lattice.__file__).resolve().parents[2]
AS_OF = "2026-09-15"
N = 14


def weekdays_ending(end: str, n: int):
    d, out = date.fromisoformat(end), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= timedelta(days=1)
    return list(reversed(out))


def make_universe():
    entries = []
    for i in range(N):
        cap = (5e8 + i * 3e8)
        entries.append({"symbol": "T%02d" % i, "cik": fx.CIK + i, "name": "Synthetic Co %d" % i, "price_usd": 20.0, "market_cap_usd": cap,
                        "median_dollar_volume_20d_usd": 20e6, "shares_outstanding": cap / 20.0, "exchange": "Nasdaq",
                        "state_of_business": "TX", "sic": "3674", "flags": [], "sina_market_cap_usd": cap, "sic_description": "x",
                        "domestic_form": "10-Q", "domestic_filed": "2026-08-04", "domestic_accession": "0001234567-26-000021"})
    return {"schema": "signal-lattice-universe/1", "as_of_date": AS_OF, "count": N, "entries": entries, "rules": {}, "content_sha256": "u" * 64,
            "generated_at": datetime.now(timezone.utc).isoformat()}


def build_world(root: Path):
    facts_path, events_path, bars_dir = root / "facts.sqlite", root / "events.sqlite", root / "bars"
    facts = FactStore(facts_path)
    universe = make_universe()
    for i, entry in enumerate(universe["entries"]):
        facts.ingest_companyfacts(entry["cik"], fx.strong_company_facts() if i % 3 else fx.weak_company_facts(), "2026-09-15")
        facts.ingest_submissions(entry["cik"], fx.submissions_payload(cik=entry["cik"]), "2026-09-15")
    facts.close()
    events = EventStore(events_path)
    events.touch_owner_first([(777001, "2019-01-01")], "test")
    events.add_buy({"accession": "0000777001-26-000001", "owner_cik": 777001, "issuer_cik": fx.CIK + 1, "symbol": "T01",
                    "owner_name": "Pat Insider", "role": "Chief Executive Officer", "filed": "2026-09-01", "accepted_at": "2026-09-01T16:05:00",
                    "first_trade": "2026-08-29", "last_trade": "2026-08-29", "shares": 10000.0, "amount_usd": 200000.0, "plan_10b5_1": 0,
                    "indirect": 0})
    events.commit()
    events.close()
    store = BarStore(bars_dir)
    rng = random.Random(11)
    days = weekdays_ending(AS_OF, 800)
    for symbol in ["T%02d" % i for i in range(N)] + ["IWM"]:
        price, rows = 20.0, []
        for d in days:
            price *= 1.0 + rng.gauss(0.0002, 0.015)
            rows.append((d, round(price, 4), 1_000_000.0))
        store.save(symbol, rows)
    return facts_path, events_path, bars_dir, universe


def market_env():
    rng = random.Random(3)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    out = {}
    for symbol, zone in (("usSPY", "America/New_York"), ("sh000300", "Asia/Shanghai"), ("hk02800", "Asia/Hong_Kong")):
        price, bars = 100.0, []
        for d in weekdays_ending(AS_OF, 400):
            o = price
            price *= 1.0 + rng.gauss(0.0003, 0.01)
            bars.append(Bar(symbol, date.fromisoformat(d), o, max(o, price) * 1.001, min(o, price) * 0.999, price, 1e6, zone, "test", epoch))
        out[symbol] = bars
    return out


class FakeHooks(RC.Hooks):
    def __init__(self, universe):
        self.universe_doc = universe
        self.collect_calls = 0

    def universe(self, cfg, log):
        return Path("/synthetic/universe.json"), self.universe_doc

    def collect(self, cfg, universe_path, universe, log):
        self.collect_calls += 1
        item = Extraction("customer_concentration", "RISK", "One customer accounted for 12% of our revenue.", "p", "Item 1", 12.0, None, "percent",
                          {"scope": "single", "lower_bound": False})
        filing = lambda cik: FilingExtraction(cik, "0001234567-26-000004", "10-K", "2026-03-02", "2025-12-31",
                                              "https://www.sec.gov/Archives/edgar/data/%d/000123456726000004/doc0004.htm" % cik, 1000,
                                              EXTRACTOR_VERSION, (item,))
        structure = {fx.CIK + i: [filing(fx.CIK + i)] for i in (0, 1, 2)}
        return RC.Collected(universe_path, universe, structure, {"coverage": {"computed": 0}, "thresholds": {}, "records": []}, market_env(),
                            {"sec_requests_total": 0 if self.collect_calls > 1 else 7})


class CycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="sl-cycle-test-"))
        cls.facts, cls.events, cls.bars, cls.universe = build_world(cls.tmp)
        cls.hooks = FakeHooks(cls.universe)
        cls.cfg = RC.CycleConfig(project_root=ROOT, work_dir=cls.tmp / "work", out_dir=cls.tmp / "out", facts_db=cls.facts, events_db=cls.events,
                                 bars_dir=cls.bars, text_cache_dir=cls.tmp / "tc", structure_cache_dir=cls.tmp / "sc", sec_cache_dir=cls.tmp / "sec",
                                 offline=True, python=sys.executable)
        cls.first = RC.run_cycle(cls.cfg, cls.hooks, log=lambda m: None)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def receipts(self, summary=None):
        return {r["branch_id"]: r for r in (summary or self.first)["receipts"]}

    def verdicts(self, branch_id, summary=None):
        return json.loads(Path(self.receipts(summary)[branch_id]["verdicts_file"]).read_text("utf-8"))

    def test_all_five_branches_participate_with_real_outputs_and_none_is_unimplemented(self):
        receipts = self.receipts()
        self.assertEqual(set(receipts), {"bottleneck-serenity-skill", "stock-commercial-opportunities", "equity-event-atlas",
                                         "equity-foresight-signal", "global-equity-lead-lag-atlas"})
        for branch_id, r in receipts.items():
            self.assertIn(r["status"], ("PASS", "ABSTAIN"), (branch_id, r["reason"], r["stderr_tail"]))
            self.assertTrue(r["verdicts_file"], branch_id)
            self.assertNotIn("UNIMPLEMENTED", json.dumps(r))
        for branch_id in ("bottleneck-serenity-skill", "stock-commercial-opportunities", "equity-event-atlas", "equity-foresight-signal"):
            self.assertEqual(sum(receipts[branch_id]["verdict_counts"].values()), N, branch_id)
        self.assertEqual(sum(receipts["global-equity-lead-lag-atlas"]["verdict_counts"].values()), 3)

    def test_receipts_share_one_snapshot_hash_and_carry_params_versions(self):
        receipts = self.receipts()
        self.assertEqual({r["snapshot_hash"] for r in receipts.values()}, {self.first["snapshot_sha256"]})
        for branch_id in ("bottleneck-serenity-skill", "stock-commercial-opportunities", "equity-event-atlas", "equity-foresight-signal"):
            self.assertRegex(receipts[branch_id]["params_version"], r"^\d+(\.\d+)+$")
            self.assertEqual(len(receipts[branch_id]["params_sha256"]), 64)
            self.assertEqual(self.verdicts(branch_id)["params"]["params_version"], receipts[branch_id]["params_version"])
            self.assertEqual(self.verdicts(branch_id)["snapshot_sha256"], self.first["snapshot_sha256"])

    def test_foresight_on_a_tiny_synthetic_pool_abstains_honestly_instead_of_publishing_a_probability(self):
        doc = self.verdicts("equity-foresight-signal")
        self.assertEqual(doc["branch_status"], "ABSTAIN")
        self.assertRegex(doc["branch_reasons"][0], r"^(SAMPLE_INSUFFICIENT|OOS_BRIER_NOT_BETTER_THAN_BASE_RATE)")
        self.assertTrue(all(v["verdict"] == "ABSTAIN" for v in doc["verdicts"]))
        self.assertIn("summary", doc["meta"])

    def test_every_pass_verdict_carries_a_sec_link(self):
        for branch_id in ("bottleneck-serenity-skill", "stock-commercial-opportunities", "equity-event-atlas", "equity-foresight-signal"):
            for v in self.verdicts(branch_id)["verdicts"]:
                if v["verdict"] == "PASS":
                    self.assertTrue(v["links"], (branch_id, v["symbol"]))
                    self.assertTrue(v["links"][0]["url"].startswith("https://www.sec.gov/"), v["links"][0])

    def test_event_atlas_finds_the_opportunistic_insider_buy_and_bottleneck_uses_the_structure_evidence(self):
        event = {v["symbol"]: v for v in self.verdicts("equity-event-atlas")["verdicts"]}
        self.assertEqual(event["T01"]["verdict"], "PASS")
        self.assertEqual(event["T01"]["label"], "POSITIVE_EVENT")
        bottleneck = {v["symbol"]: v for v in self.verdicts("bottleneck-serenity-skill")["verdicts"]}
        self.assertEqual(bottleneck["T00"]["evidence"]["structure"]["counts"]["customer_concentration"], {"RISK": 1})
        self.assertIsNone(bottleneck["T05"]["evidence"]["structure"])          # 没有抽取的公司不带结构性证据

    def test_lead_lag_is_market_environment_only_and_never_a_stock_pick(self):
        doc = self.verdicts("global-equity-lead-lag-atlas")
        self.assertEqual(doc["meta"]["role"], "MARKET_ENVIRONMENT_INPUT_NOT_STOCK_PICKING")
        shortlist = json.loads(Path(self.first["shortlist_file"]).read_text("utf-8"))
        self.assertNotIn("global-equity-lead-lag-atlas", json.dumps(shortlist["entries"]))
        self.assertTrue({e["symbol"] for e in shortlist["entries"]} <= {"T%02d" % i for i in range(N)})

    def test_shortlist_is_union_of_passes_and_branch_tops_within_the_cap(self):
        shortlist = json.loads(Path(self.first["shortlist_file"]).read_text("utf-8"))
        self.assertLessEqual(shortlist["count"], RC.SHORTLIST_MAX)
        self.assertEqual(shortlist["snapshot_sha256"], self.first["snapshot_sha256"])
        symbols = [e["symbol"] for e in shortlist["entries"]]
        self.assertEqual(len(symbols), len(set(symbols)))
        self.assertIn("T01", symbols)
        item = next(e for e in shortlist["entries"] if e["symbol"] == "T01")
        self.assertIn("equity-event-atlas", item["passed_by"])
        self.assertTrue(item["links"]["equity-event-atlas"]["url"].startswith("https://www.sec.gov/"))
        for e in shortlist["entries"]:
            self.assertTrue(e["passed_by"] or e["top_in"])
        self.assertEqual([e["rank"] for e in shortlist["entries"]], list(range(1, len(symbols) + 1)))

    def test_shortlist_rule_on_receipts(self):
        def receipt(branch, status, verdicts, tmp):
            path = tmp / (branch + ".json")
            path.write_text(json.dumps({"verdicts": verdicts}), "utf-8")
            return BranchReceipt(branch, status, None, "h", "1", "s", "1", "a", "b", 0.0, 0, verdicts_file=str(path))

        def v(sym, verdict, score, rank=None):
            return {"symbol": sym, "cik": 1, "name": sym, "market_cap_usd": 1e9, "verdict": verdict, "score": score, "rank_key": rank or score, "links": []}

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            bottleneck = receipt("bottleneck-serenity-skill", "PASS", [v("A", "PASS", 70), v("B", "ABSTAIN", 40), v("C", "FAILED", 99), v("D", "ABSTAIN", 0)], tmp)
            foresight = receipt("equity-foresight-signal", "ABSTAIN", [v("E", "ABSTAIN", 0)], tmp)
            lead = receipt("global-equity-lead-lag-atlas", "PASS", [v("usSPY", "PASS", 0.5)], tmp)
            out = RC.build_shortlist([bottleneck, foresight, lead], top_n=1, cap=5)
            self.assertEqual([e["symbol"] for e in out], ["A"])                # top-1 = A（PASS，分数最高）；B 没进前 1；FAILED 与零分不入选
            out = RC.build_shortlist([bottleneck, foresight, lead], top_n=5, cap=5)
            self.assertEqual([e["symbol"] for e in out], ["A", "B"])          # FAILED(C=99) 与 0 分(D)、ABSTAIN 的整分支(E)、全球联动都不进

    def test_second_run_on_the_same_snapshot_reuses_results_and_counts_nothing_twice(self):
        cycle_files = sorted((self.cfg.out_dir / AS_OF).glob("cycle-*.json"))
        second = RC.run_cycle(self.cfg, self.hooks, log=lambda m: None)
        self.assertTrue(second["reused"])
        self.assertEqual(second["branch_runs_this_invocation"], 0)
        self.assertEqual(second["snapshot_sha256"], self.first["snapshot_sha256"])
        self.assertEqual(second["shortlist_count"], self.first["shortlist_count"])
        self.assertEqual(sorted((self.cfg.out_dir / AS_OF).glob("cycle-*.json")), cycle_files)      # 没有新增第二份
        self.assertEqual(len(list((self.cfg.out_dir / AS_OF).glob("shortlist-*.json"))), 1)
        self.assertEqual(second["collection_this_invocation"]["sec_requests_total"], 0)             # 第二次采集 0 请求
        self.assertEqual(json.loads((self.cfg.out_dir / AS_OF / "latest.json").read_text("utf-8"))["snapshot_sha256"], self.first["snapshot_sha256"])

    def test_forced_rerun_reproduces_every_verdict_file_byte_for_byte(self):
        import dataclasses
        forced_cfg = dataclasses.replace(self.cfg, force=True, out_dir=self.tmp / "out-forced")
        forced = RC.run_cycle(forced_cfg, self.hooks, log=lambda m: None)
        self.assertFalse(forced["reused"])
        self.assertEqual(forced["snapshot_sha256"], self.first["snapshot_sha256"])                 # 数据没变 -> 快照 hash 不变
        a, b = self.receipts(), self.receipts(forced)
        for branch_id in a:
            self.assertEqual(a[branch_id]["verdicts_sha256"], b[branch_id]["verdicts_sha256"], branch_id)

    def test_report_prints_counts_receipts_shortlist_and_brier_block(self):
        text = RC.render_report(self.first, top=5)
        for needle in ("PASS", "snapshot_hash=", "params_version=", "shortlist 前 5", "所有收据的 snapshot_hash 相同：是", "样本外 Brier"):
            self.assertIn(needle, text)
        self.assertNotIn("UNIMPLEMENTED", text)


if __name__ == "__main__":
    unittest.main()
