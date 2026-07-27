#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "equity_event_atlas.py"
FIXTURES = SKILL_ROOT / "fixtures"
SPEC = importlib.util.spec_from_file_location("equity_event_atlas", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class EquityEventAtlasTests(unittest.TestCase):
    def load(self, relative: str):
        path = FIXTURES / relative
        return path, json.loads(path.read_text(encoding="utf-8"))

    def codes(self, relative: str):
        path, value = self.load(relative)
        return {issue.code for issue in MODULE.validate_bundle(value, path.parent)}

    def test_valid_us_request(self):
        _, value = self.load("valid_request_us.json")
        self.assertEqual([], MODULE.validate_request(value))

    def test_valid_asx_request(self):
        _, value = self.load("valid_request_asx.json")
        self.assertEqual([], MODULE.validate_request(value))

    def test_valid_global_request(self):
        _, value = self.load("valid_request_global.json")
        self.assertEqual([], MODULE.validate_request(value))

    def test_valid_bundle(self):
        path, value = self.load("valid_bundle_synthetic.json")
        self.assertEqual([], MODULE.validate_bundle(value, path.parent))

    def test_probability_sum_gate(self):
        self.assertIn("PROBABILITY_SUM_INVALID", self.codes("invalid/probability_sum.json"))

    def test_fact_evidence_gate(self):
        self.assertIn("FACT_WITHOUT_EVIDENCE", self.codes("invalid/fact_without_evidence.json"))

    def test_action_context_gate(self):
        self.assertIn("USER_CONTEXT_INSUFFICIENT", self.codes("invalid/action_without_context.json"))

    def test_point_in_time_gate(self):
        self.assertIn("POINT_IN_TIME_LEAK", self.codes("invalid/point_in_time_leak.json"))

    def test_event_reference_gate(self):
        self.assertIn("EVENT_REF_MISSING", self.codes("invalid/event_reference.json"))

    def test_market_gate(self):
        self.assertIn("OFFICIAL_SOURCE_GATE", self.codes("invalid/market_gate.json"))

    def test_us_full_capability(self):
        result = MODULE.market_capability(
            "XNAS", official_sources_verified=True, calendar_verified=True, market_data_verified=True
        )
        self.assertEqual("DEEP", result["coverage_tier"])
        self.assertEqual("FULL", result["run_capability"])

    def test_asx_full_capability(self):
        result = MODULE.market_capability(
            "XASX", official_sources_verified=True, calendar_verified=True, market_data_verified=True
        )
        self.assertEqual("DEEP", result["coverage_tier"])
        self.assertEqual("FULL", result["run_capability"])

    def test_generic_market_is_capability_gated(self):
        result = MODULE.market_capability(
            "XLON", official_sources_verified=True, calendar_verified=True, market_data_verified=True
        )
        self.assertEqual("GENERIC", result["coverage_tier"])
        self.assertEqual("SUPPORTED_WITH_HOST_DATA", result["run_capability"])

    def test_unknown_market_without_official_source_is_blocked(self):
        result = MODULE.market_capability(
            "ZZZZ", official_sources_verified=False, calendar_verified=False, market_data_verified=False
        )
        self.assertEqual("BLOCKED", result["run_capability"])

    def test_render_is_byte_deterministic(self):
        source = FIXTURES / "valid_bundle_synthetic.json"
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            MODULE.render_bundle(source, Path(first))
            MODULE.render_bundle(source, Path(second))
            self.assertEqual(MODULE.tree_digest(Path(first)), MODULE.tree_digest(Path(second)))

    def test_cli_self_test(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "self-test", "--fixtures", str(FIXTURES), "--repeat", "3"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual("PASS", result["status"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
