from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("portfolio", ROOT / "scripts" / "analyze_portfolio_clusters.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class PortfolioTests(unittest.TestCase):
    @staticmethod
    def metadata():
        return {
            "schema_version": "1.0",
            "skill_version": "0.0.0.1",
            "as_of": "2026-07-22",
            "source_cutoff": "2026-07-21",
            "previous_version": None,
        }

    def test_illustrative_analysis_snapshot_matches_script_output(self):
        payload = json.loads(
            (ROOT / "examples" / "illustrative_portfolio.json").read_text(
                encoding="utf-8"
            )
        )
        expected = (
            ROOT / "examples" / "illustrative_portfolio_analysis.json"
        ).read_text(encoding="utf-8")
        observed = json.dumps(
            MODULE.analyze_portfolio(payload), ensure_ascii=False, indent=2
        ) + "\n"
        self.assertEqual(observed, expected)

    def test_root_driver_concentration_flagged(self):
        payload = {
            **self.metadata(),
            "positions": [
                {"ticker": "A", "weight": 0.2, "drivers": ["ai-capex"], "constraints": ["optics"]},
                {"ticker": "B", "weight": 0.2, "drivers": ["ai-capex"], "constraints": ["memory"]}
            ]
        }
        result = MODULE.analyze_portfolio(payload)
        self.assertTrue(any(a["type"] == "root_driver" for a in result["alerts"]))

    def test_pair_overlap_detected(self):
        payload = {
            **self.metadata(),
            "positions": [
                {"ticker": "A", "weight": 0.1, "drivers": ["ai"], "constraints": ["optics"], "customers": ["hyper"]},
                {"ticker": "B", "weight": 0.1, "drivers": ["ai"], "constraints": ["optics"], "customers": ["hyper"]}
            ]
        }
        result = MODULE.analyze_portfolio(payload)
        self.assertGreaterEqual(len(result["pair_overlaps"]), 1)
        self.assertEqual(
            {key: result[key] for key in self.metadata()}, self.metadata()
        )

    def test_missing_artifact_metadata_rejected(self):
        payload = {**self.metadata(), "positions": []}
        del payload["skill_version"]
        with self.assertRaises(ValueError):
            MODULE.analyze_portfolio(payload)

    def test_previous_version_presence_is_required(self):
        linked = {**self.metadata(), "previous_version": "snapshot-0001", "positions": []}
        self.assertEqual(
            MODULE.analyze_portfolio(linked)["previous_version"], "snapshot-0001"
        )

        for mutation in ("missing", "renamed"):
            with self.subTest(mutation=mutation):
                payload = {**self.metadata(), "positions": []}
                previous_version = payload.pop("previous_version")
                if mutation == "renamed":
                    payload["renamed_previous_version"] = previous_version
                with self.assertRaisesRegex(ValueError, "previous_version is required"):
                    MODULE.analyze_portfolio(payload)


if __name__ == "__main__":
    unittest.main()
