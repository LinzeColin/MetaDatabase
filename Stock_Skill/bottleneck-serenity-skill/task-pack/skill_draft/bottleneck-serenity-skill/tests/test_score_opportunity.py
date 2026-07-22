from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("score_opportunity", ROOT / "scripts" / "score_opportunity.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def full_payload(rating: float = 4.0):
    payload = json.loads(json.dumps(MODULE.TEMPLATE))
    payload["as_of"] = "2026-07-22"
    payload["source_cutoff"] = "2026-07-21"
    for factors in payload["scores"].values():
        for key in factors:
            factors[key] = rating
    payload["clocks"].update(
        {
            "scarcity_p10_months": 12,
            "scarcity_p50_months": 36,
            "scarcity_p90_months": 60,
            "monetization_lag_months": 6,
            "market_discovery_months": 6,
            "contracted_forward_ramp": True,
        }
    )
    payload["scenarios"] = {
        "bear": {"probability": 0.25, "return_pct": -30},
        "base": {"probability": 0.50, "return_pct": 35},
        "bull": {"probability": 0.25, "return_pct": 90},
    }
    return payload


class ScoreOpportunityTests(unittest.TestCase):
    def test_strong_case_is_priority_or_candidate(self):
        result = MODULE.score_payload(full_payload())
        self.assertIn(result["decision"]["label"], {"RESEARCH_PRIORITY", "CANDIDATE"})
        self.assertTrue(result["decision"]["hard_gates_passed"])
        self.assertEqual(
            {key: result[key] for key in (
                "schema_version", "skill_version", "as_of", "source_cutoff", "previous_version"
            )},
            {
                "schema_version": "1.0",
                "skill_version": "0.0.0.1",
                "as_of": "2026-07-22",
                "source_cutoff": "2026-07-21",
                "previous_version": None,
            },
        )

    def test_no_revenue_bridge_overrides_score(self):
        payload = full_payload()
        payload["hard_flags"]["no_material_revenue_bridge"] = True
        result = MODULE.score_payload(payload)
        self.assertEqual(result["decision"]["label"], "BOTTLENECK_NOT_EQUITY")

    def test_no_primary_evidence_overrides_score(self):
        payload = full_payload()
        payload["hard_flags"]["no_primary_evidence"] = True
        result = MODULE.score_payload(payload)
        self.assertEqual(result["decision"]["label"], "WATCH_EVIDENCE")

    def test_low_mispricing_is_priced(self):
        payload = full_payload()
        for key in payload["scores"]["mispricing"]:
            payload["scores"]["mispricing"][key] = 2.0
        result = MODULE.score_payload(payload)
        self.assertEqual(result["decision"]["label"], "WATCH_PRICED")

    def test_invalid_probability_rejected(self):
        payload = full_payload()
        payload["scenarios"]["bear"]["probability"] = 0.5
        with self.assertRaises(ValueError):
            MODULE.score_payload(payload)

    def test_missing_or_wrong_artifact_metadata_rejected(self):
        for field, replacement in (
            ("schema_version", None),
            ("skill_version", "v0.0.0.1"),
            ("source_cutoff", "2026-07-23"),
            ("previous_version", 1),
        ):
            with self.subTest(field=field):
                payload = full_payload()
                if replacement is None and field == "schema_version":
                    del payload[field]
                else:
                    payload[field] = replacement
                with self.assertRaises(ValueError):
                    MODULE.score_payload(payload)

    def test_previous_version_presence_is_required(self):
        linked = full_payload()
        linked["previous_version"] = "snapshot-0001"
        self.assertEqual(
            MODULE.score_payload(linked)["previous_version"], "snapshot-0001"
        )

        for mutation in ("missing", "renamed"):
            with self.subTest(mutation=mutation):
                payload = full_payload()
                previous_version = payload.pop("previous_version")
                if mutation == "renamed":
                    payload["renamed_previous_version"] = previous_version
                with self.assertRaisesRegex(ValueError, "previous_version is required"):
                    MODULE.score_payload(payload)


if __name__ == "__main__":
    unittest.main()
