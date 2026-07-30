from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_evidence", ROOT / "scripts" / "validate_evidence.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class EvidenceTests(unittest.TestCase):
    @staticmethod
    def metadata():
        return {
            "schema_version": "1.0",
            "skill_version": "0.0.0.1",
            "as_of": "2026-07-22",
            "source_cutoff": "2026-07-22",
            "previous_version": None,
        }

    def test_critical_fact_with_independent_primary_passes(self):
        payload = {
            **self.metadata(),
            "claims": [
                {
                    "id": "C1",
                    "claim": "Illustrative capacity is constrained.",
                    "claim_type": "fact",
                    "critical": True,
                    "status": "supported",
                    "contradiction_search": "Searched announced capacity and substitutes.",
                    "sources": [
                        {"url": "https://a.example", "publisher": "Issuer", "date": "2026-07-01", "tier": "A", "independence_group": "issuer-filing", "stance": "supports"},
                        {"url": "https://b.example", "publisher": "Customer", "date": "2026-07-02", "tier": "A", "independence_group": "customer-filing", "stance": "supports"}
                    ]
                }
            ]
        }
        result = MODULE.validate_ledger(payload)
        self.assertTrue(result["valid"])
        self.assertEqual(
            {key: result[key] for key in self.metadata()}, self.metadata()
        )

    def test_echo_sources_fail_independence(self):
        payload = {
            **self.metadata(),
            "claims": [
                {
                    "id": "C1",
                    "claim": "Illustrative sole-source claim.",
                    "claim_type": "fact",
                    "critical": True,
                    "status": "supported",
                    "sources": [
                        {"url": "https://a.example", "publisher": "Issuer", "date": "2026-07-01", "tier": "A", "independence_group": "same-release", "stance": "supports"},
                        {"url": "https://b.example", "publisher": "News", "date": "2026-07-02", "tier": "C", "independence_group": "same-release", "stance": "supports"}
                    ]
                }
            ]
        }
        result = MODULE.validate_ledger(payload)
        self.assertFalse(result["valid"])
        self.assertTrue(any("independent" in item for item in result["errors"]))

    def test_missing_artifact_metadata_rejected(self):
        payload = {**self.metadata(), "claims": []}
        del payload["source_cutoff"]
        with self.assertRaises(ValueError):
            MODULE.validate_ledger(payload)

    def test_previous_version_presence_is_required(self):
        linked = {**self.metadata(), "previous_version": "snapshot-0001", "claims": []}
        self.assertEqual(
            MODULE.validate_ledger(linked)["previous_version"], "snapshot-0001"
        )

        for mutation in ("missing", "renamed"):
            with self.subTest(mutation=mutation):
                payload = {**self.metadata(), "claims": []}
                previous_version = payload.pop("previous_version")
                if mutation == "renamed":
                    payload["renamed_previous_version"] = previous_version
                with self.assertRaisesRegex(ValueError, "previous_version is required"):
                    MODULE.validate_ledger(payload)


if __name__ == "__main__":
    unittest.main()
