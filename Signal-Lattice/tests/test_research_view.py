"""实时层读研究层产物：结构、全池排名、以及每一种「读不全」都变成明确的问题（由中枢转成 SYSTEM_BLOCKED）。"""

import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from signal_lattice import hub
from signal_lattice.research_view import load_research
from hub_fixtures import BOTTLENECK, COMMERCIAL, EVENT, NOW, open_proof, standard_pool, write_research_dir


class LoadTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_loads_receipts_verdicts_ranks_shortlist_and_pool(self):
        write_research_dir(self.root, standard_pool())
        view = load_research(self.root)
        self.assertEqual(view.problems, [])
        self.assertEqual(view.as_of, "2026-09-29")
        self.assertEqual(set(view.receipts), {EVENT, COMMERCIAL, BOTTLENECK, "equity-foresight-signal", "global-equity-lead-lag-atlas"})
        self.assertEqual(view.receipts[EVENT]["verdict_counts"]["PASS"], 2)
        self.assertEqual(view.ranks[COMMERCIAL]["k"], 3)
        self.assertIn("ALPHA", {e["symbol"] for e in view.shortlist})
        self.assertEqual(view.pool["ALPHA"]["exchange"], "NYSE")
        self.assertEqual(view.verdict(EVENT, "ALPHA")["verdict"], "PASS")

    def test_the_loaded_view_produces_the_same_decision_as_the_in_memory_one(self):
        write_research_dir(self.root, standard_pool())
        view = load_research(self.root)
        outcome = hub.decide(view, {e["symbol"]: {"price": 10.0, "quote_status": "FRESH"} for e in view.shortlist}, now=NOW, proof=open_proof())
        self.assertEqual(outcome["decision"]["primary_symbol"], "ALPHA")

    def test_empty_directory_is_a_research_missing_problem(self):
        self.assertEqual(load_research(self.root).problems[0].split(":")[0], "RESEARCH_MISSING")

    def test_shortlist_from_another_snapshot_is_a_problem(self):
        write_research_dir(self.root, standard_pool())
        day = self.root / "2026-09-29"
        pointer = json.loads((day / "latest.json").read_text())
        pointer["snapshot_sha256"] = "c" * 64
        (day / "latest.json").write_text(json.dumps(pointer))
        codes = {p.split(":")[0] for p in load_research(self.root).problems}
        self.assertIn("SNAPSHOT_MISMATCH", codes)
        self.assertIn("BRANCH_SNAPSHOT_MISMATCH", codes)

    def test_a_missing_verdict_file_and_a_failed_branch_are_problems(self):
        write_research_dir(self.root, standard_pool(), statuses={BOTTLENECK: "FAILED"})
        (next((self.root / "2026-09-29" / "branches" / COMMERCIAL).glob("verdicts-*.json"))).unlink()
        codes = [p.split(":")[0] for p in load_research(self.root).problems]
        self.assertIn("BRANCH_FAILED", codes)
        self.assertIn("VERDICTS_MISSING", codes)

    def test_missing_hub_inputs_are_a_problem_and_the_hub_blocks_with_a_plain_message(self):
        write_research_dir(self.root, standard_pool(), hubinputs=False)
        view = load_research(self.root)
        self.assertTrue(any(p.startswith("HUBINPUTS_MISSING") for p in view.problems))
        decision = hub.decide(view, {}, now=NOW)["decision"]
        self.assertEqual(decision["state"], "SYSTEM_BLOCKED")
        self.assertIn("缺少中枢输入文件", decision["message"])

    def test_newest_day_directory_wins(self):
        write_research_dir(self.root, standard_pool(), as_of="2026-09-28")
        write_research_dir(self.root, standard_pool(), as_of="2026-09-29")
        self.assertEqual(load_research(self.root).as_of, "2026-09-29")

    def test_artifacts_moved_to_another_directory_are_still_found(self):
        write_research_dir(self.root, standard_pool())
        cycle = next((self.root / "2026-09-29").glob("cycle-*.json"))
        payload = json.loads(cycle.read_text())
        for receipt in payload["receipts"]:
            receipt["verdicts_file"] = "/somewhere/else/" + Path(receipt["verdicts_file"]).name
        cycle.write_text(json.dumps(payload))
        self.assertEqual(load_research(self.root).problems, [])

    def test_age_uses_the_later_of_generation_and_the_last_research_check(self):
        write_research_dir(self.root, standard_pool(), generated_at=NOW - timedelta(hours=60), checked_at=NOW - timedelta(hours=3))
        self.assertAlmostEqual(load_research(self.root).age_hours(NOW), 3.0, places=3)


if __name__ == "__main__":
    unittest.main()
