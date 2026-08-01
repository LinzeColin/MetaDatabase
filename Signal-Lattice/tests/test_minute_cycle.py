from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from signal_lattice.clock import FakeClock
from signal_lattice.config import Settings
from signal_lattice.cycle_engine import run_minute_cycle
from signal_lattice.db import RuntimeDB


class MinuteCycleNorthStarTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = Path(__file__).resolve().parents[1]
        self.t0 = datetime(2026, 7, 30, 10, 15, 8, tzinfo=timezone.utc)
        self.db = RuntimeDB(self.root / "runtime.db", self.project / "db" / "schema.sql", FakeClock(self.t0))

    def tearDown(self):
        self.temp.cleanup()

    def run_cycle(self, now, settings=None):
        with patch("signal_lattice.skill_registry.ensure_agent_checkout", return_value=(None, None, "TEST_OFFLINE")):
            return run_minute_cycle(self.db, settings or self.settings(), now=now)

    def settings(self, **overrides):
        values = dict(
            state_dir=self.root / "state",
            artifact_dir=self.root / "artifacts",
            web_dir=self.project / "web",
            runtime_environment="prebuild",
            decision_policy_path=self.project / "config" / "decision_policy.json",
            market_provider="fixture",
            universe_path=self.project / "config" / "universe.json",
            runtime_manifest_dir=self.project / "config" / "runtime_manifests",
            upstream_checkout_dir=self.root / "upstream",
            cycle_deadline_seconds=55,
            skill_timeout_seconds=8,
            minimum_active_skills=5,
            minimum_completed_skills=3,
        )
        values.update(overrides)
        return Settings(**values)

    def test_every_active_skill_runs_and_exactly_one_recommendation_is_created(self):
        result = self.run_cycle(self.t0)
        self.assertEqual(result["state"], "COMPLETED")
        self.assertGreaterEqual(result["active_skill_count"], 5)
        self.assertEqual(result["completed_skill_count"], result["active_skill_count"])
        self.assertEqual(result["failed_skill_count"], 0)
        self.assertEqual(len(result["skill_runs"]), result["active_skill_count"])
        recommendation = result["recommendation"]
        self.assertIn(recommendation["action"], {"BUY", "ADD", "HOLD", "REDUCE", "SELL", "WATCH", "AVOID", "NO_ACTION"})
        self.assertNotEqual(recommendation["action"], "SYSTEM_BLOCKED")
        self.assertTrue(recommendation["full_cycle_completed"])
        self.assertEqual(recommendation["active_skill_count"], result["active_skill_count"])
        self.assertEqual(len(recommendation["skill_judgements"]), result["active_skill_count"])
        market_hashes = {run["input_sha256"] for run in result["skill_runs"]}
        self.assertEqual(len(market_hashes), result["active_skill_count"], "Each isolated input also binds its own manifest")
        with self.db.connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM minute_cycles").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT count(*) FROM outbox WHERE event_type='minute.recommendation.created'").fetchone()[0], 1)

    def test_same_minute_is_idempotent_and_next_minute_creates_new_cycle(self):
        first = self.run_cycle(self.t0)
        second = self.run_cycle(self.t0 + timedelta(seconds=20))
        self.assertEqual(first["cycle_id"], second["cycle_id"])
        with self.db.connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM minute_cycles").fetchone()[0], 1)
        third = self.run_cycle(self.t0 + timedelta(minutes=1))
        self.assertNotEqual(first["cycle_id"], third["cycle_id"])
        with self.db.connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM minute_cycles").fetchone()[0], 2)

    def test_missing_market_data_is_system_blocked_not_no_action(self):
        missing = self.root / "missing-market.json"
        with patch.dict(os.environ, {"SIGNAL_LATTICE_MARKET_FIXTURE": str(missing)}, clear=False):
            result = self.run_cycle(self.t0)
        self.assertEqual(result["state"], "FAILED")
        self.assertEqual(result["recommendation"]["action"], "SYSTEM_BLOCKED")
        self.assertFalse(result["recommendation"]["full_cycle_completed"])

    def test_complete_cycle_with_failed_investment_gates_is_valid_no_action(self):
        fixture = json.loads((self.project / "fixtures" / "northstar_market.json").read_text(encoding="utf-8"))
        # Force all candidates below liquidity/capacity and with prohibitive transaction costs,
        # while keeping the complete data-production chain intact.
        for row in fixture["universe"]:
            row["liquidity_score"] = 0.01
            row["daily_value_traded_usd"] = 1_000.0
            row["capacity_usd"] = 10.0
            row["cost_bps"] = 10_000.0
        fixture_path = self.root / "blocked-gates.json"
        fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
        with patch.dict(os.environ, {"SIGNAL_LATTICE_MARKET_FIXTURE": str(fixture_path)}, clear=False):
            result = self.run_cycle(self.t0)
        self.assertEqual(result["state"], "COMPLETED")
        self.assertEqual(result["completed_skill_count"], result["active_skill_count"])
        recommendation = result["recommendation"]
        self.assertEqual(recommendation["action"], "NO_ACTION")
        self.assertTrue(recommendation["full_cycle_completed"])
        self.assertNotIn("ALL_SKILLS_ABSTAINED_AFTER_COMPLETE_EXECUTION", recommendation["reasons"])
        self.assertTrue(any(reason.startswith("INVESTMENT_GATE_FAILED:") for reason in recommendation["reasons"]))

    def test_production_rejects_fixture_provider(self):
        env = {
            "SIGNAL_LATTICE_ENV": "production",
            "SIGNAL_LATTICE_MARKET_PROVIDER": "fixture",
            "SIGNAL_LATTICE_STATE_DIR": str(self.root / "state"),
            "SIGNAL_LATTICE_ARTIFACT_DIR": str(self.root / "artifacts"),
        }
        with patch.dict(os.environ, env, clear=False), self.assertRaisesRegex(ValueError, "PRODUCTION_REQUIRES_LIVE_APPROVED_MARKET_PROVIDER"):
            Settings.from_env(self.project)


if __name__ == "__main__":
    unittest.main()
