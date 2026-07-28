from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.run_assurance_002_acceptance import (
    EXPECTED_ACCEPTANCES,
    EXPECTED_EXECUTION,
    EXPECTED_FEATURE_GATES,
    MISSING_PRIVATE_GOLD_ACTIONS,
    _environment,
    _probe_missing_private_gold,
    _validate_feature_gates,
)


class Assurance002Tests(unittest.TestCase):
    def test_disabled_model_gate_requires_private_gold_for_quality_claims(self) -> None:
        feature_gate = _validate_feature_gates()
        self.assertEqual(feature_gate["feature_gates"], EXPECTED_FEATURE_GATES)
        self.assertEqual(feature_gate["model_dataset"]["red_team_contract_cases"], 3)
        with tempfile.TemporaryDirectory(prefix="x2n-a002-test-") as temporary:
            probe = _probe_missing_private_gold(_environment(Path(temporary)))
        self.assertEqual(probe["commands"], len(MISSING_PRIVATE_GOLD_ACTIONS))
        self.assertEqual(probe["safe_failures"], len(MISSING_PRIVATE_GOLD_ACTIONS))

    def test_public_aggregate_receipt_has_no_private_content_or_local_path(self) -> None:
        rendered = json.dumps(
            {
                "acceptance_status": EXPECTED_ACCEPTANCES,
                "execution": EXPECTED_EXECUTION,
                "feature_gates": EXPECTED_FEATURE_GATES,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        self.assertNotIn("/" + "Users/", rendered)
        self.assertNotIn("/" + "home/", rendered)
        self.assertNotIn("github" + "_pat_", rendered)
        self.assertNotIn("Bearer" + " ", rendered)
        self.assertNotIn("not-present", rendered)


if __name__ == "__main__":
    unittest.main()
