from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from signal_lattice.clock import FakeClock
from signal_lattice.config import CANONICAL_STOCK_SKILL_SPARSE_PATH, Settings
from signal_lattice.db import RuntimeDB
from signal_lattice.skill_registry import RuntimeManifest, reconcile_runtime_registry


class SkillRegistryLastKnownGoodTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = Path(__file__).resolve().parents[1]
        self.db = RuntimeDB(
            self.root / "runtime.db",
            self.project / "db" / "schema.sql",
            FakeClock(datetime(2026, 7, 30, tzinfo=timezone.utc)),
        )
        self.settings = Settings(
            state_dir=self.root / "state",
            artifact_dir=self.root / "artifacts",
            web_dir=self.project / "web",
            decision_policy_path=self.project / "config" / "decision_policy.json",
            market_provider="fixture",
            universe_path=self.project / "config" / "universe.json",
            runtime_manifest_dir=self.project / "config" / "runtime_manifests",
            upstream_checkout_dir=self.root / "upstream",
        )
        self.now = "2026-07-30T00:00:00+00:00"

    def tearDown(self):
        self.temp.cleanup()

    def seed(self, skill_id: str, profile: str = "commercial_opportunity") -> RuntimeManifest:
        manifest = RuntimeManifest(
            skill_id=skill_id,
            display_name=skill_id,
            skill_version="1.0.0",
            runtime_profile=profile,
            source_repository="https://github.com/example/upstream.git",
            source_path=f"{CANONICAL_STOCK_SKILL_SPARSE_PATH}/{skill_id}",
            source_commit="a" * 40,
            source_sha256="b" * 64,
        )
        self.db.upsert_runtime_skill(manifest.as_json(), manifest.manifest_sha256, self.now)
        return manifest

    def make_checkout(self, entries: list[dict]) -> Path:
        checkout = self.root / "checkout"
        stock = checkout / "Signal-Lattice" / "Stock_Skill"
        stock.mkdir(parents=True, exist_ok=True)
        (stock / "REGISTRY.json").write_text(json.dumps({"skills": entries}), encoding="utf-8")
        for entry in entries:
            path = stock / str(entry.get("path") or entry["skill_id"])
            path.mkdir(parents=True, exist_ok=True)
            (path / "SKILL.md").write_text(f"# {entry['skill_id']}\n", encoding="utf-8")
        return checkout

    def test_transient_upstream_failure_preserves_active_last_known_good(self):
        seeded = self.seed("custom-lkg")
        with patch("signal_lattice.skill_registry.ensure_sparse_checkout", return_value=(None, None, "UPSTREAM_FETCH_FAILED")), patch("signal_lattice.skill_registry.ensure_agent_checkout", return_value=(None, None, "TEST_OFFLINE")):
            receipt = reconcile_runtime_registry(self.db, self.settings, now=self.now)
        self.assertEqual(receipt["state"], "DEGRADED_USE_LAST_KNOWN_GOOD")
        self.assertTrue(receipt["last_known_good_preserved"])
        active = {row["skill_id"]: row for row in self.db.active_runtime_skills()}
        self.assertIn("custom-lkg", active)
        self.assertEqual(active["custom-lkg"]["manifest_sha256"], seeded.manifest_sha256)

    def test_default_uses_the_canonical_nested_stock_skill_path(self):
        self.assertEqual(self.settings.upstream_sparse_path, CANONICAL_STOCK_SKILL_SPARSE_PATH)

    def test_incompatible_update_is_quarantined_while_prior_active_version_remains(self):
        seeded = self.seed("future-skill")
        checkout = self.make_checkout([
            {"skill_id": "future-skill", "path": "future-skill", "version": "2.0.0"}
        ])
        with patch("signal_lattice.skill_registry.ensure_sparse_checkout", return_value=(checkout, "c" * 40, None)), patch("signal_lattice.skill_registry.ensure_agent_checkout", return_value=(None, None, "TEST_OFFLINE")):
            receipt = reconcile_runtime_registry(self.db, self.settings, now=self.now)
        active = {row["skill_id"]: row for row in self.db.active_runtime_skills()}
        self.assertIn("future-skill", active)
        self.assertEqual(active["future-skill"]["manifest_sha256"], seeded.manifest_sha256)
        self.assertTrue(any(item.get("skill_id") == "future-skill" and item.get("reason") == "NO_DETERMINISTIC_RUNTIME_ADAPTER" for item in receipt["quarantined"]))
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT event_type,skill_id FROM source_reconcile_events ORDER BY created_at DESC"
            ).fetchall()
        self.assertTrue(any(row["event_type"] == "UPDATE_QUARANTINED_KEEP_LKG" and row["skill_id"] == "future-skill" for row in rows))

    def test_successfully_parsed_omission_retires_removed_skill(self):
        self.seed("obsolete-skill")
        checkout = self.make_checkout([
            {
                "skill_id": "stock-commercial-opportunities",
                "path": "stock-commercial-opportunities",
                "version": "1.0.0",
            }
        ])
        with patch("signal_lattice.skill_registry.ensure_sparse_checkout", return_value=(checkout, "d" * 40, None)), patch("signal_lattice.skill_registry.ensure_agent_checkout", return_value=(None, None, "TEST_OFFLINE")):
            receipt = reconcile_runtime_registry(self.db, self.settings, now=self.now)
        active = {row["skill_id"] for row in self.db.active_runtime_skills()}
        self.assertNotIn("obsolete-skill", active)
        self.assertTrue(any(event["event_type"] == "REMOVED" and event["skill_id"] == "obsolete-skill" for event in receipt["events"]))


if __name__ == "__main__":
    unittest.main()
