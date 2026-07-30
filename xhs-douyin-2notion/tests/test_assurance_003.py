from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.run_assurance_003_acceptance import (
    EXPECTED_ACCEPTANCES,
    EXPECTED_EXECUTION,
    EXPECTED_REPORTS,
    _environment,
    _history_scan,
    _nomenclature,
    _zero_auth_boundary,
)


class Assurance003Tests(unittest.TestCase):
    def test_history_scan_is_aggregate_only_and_zero_finding(self) -> None:
        with tempfile.TemporaryDirectory(prefix="x2n-a003-test-") as temporary:
            report = _history_scan(env=_environment(Path(temporary)))
        self.assertGreater(report["commits_scanned"], 0)
        self.assertGreaterEqual(report["pattern_classes"], 5)
        self.assertEqual(report["credential_history_hits"], 0)

    def test_auth_and_active_runtime_boundaries_remain_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="x2n-a003-auth-") as temporary:
            auth = _zero_auth_boundary(env=_environment(Path(temporary)))
        terminology = _nomenclature()
        self.assertEqual(auth["credential_helpers_touched"], 0)
        self.assertEqual(auth["secret_reads"], 0)
        self.assertEqual(terminology["active_legacy_aliases"], 0)

    def test_public_receipt_is_fixed_to_security_only_aggregates(self) -> None:
        self.assertEqual(len(EXPECTED_ACCEPTANCES), 6)
        self.assertEqual(EXPECTED_EXECUTION["platform_calls"], 0)
        self.assertEqual(EXPECTED_EXECUTION["secret_reads"], 0)
        self.assertEqual(EXPECTED_REPORTS["history"]["credential_history_hits"], 0)
        self.assertEqual(EXPECTED_REPORTS["osv"]["critical_high_unresolved"], 0)


if __name__ == "__main__":
    unittest.main()
