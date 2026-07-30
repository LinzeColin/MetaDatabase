from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from equity_foresight_signal import assess_workload, build_capacity_contract
from equity_foresight_signal.canonical import sha256_hex
from equity_foresight_signal.errors import EFSError

ROOT = Path(__file__).resolve().parents[1]


def load(name: str) -> dict:
    return json.loads((ROOT / "fixtures" / name).read_text(encoding="utf-8"))


class CapacityContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = load("bundle.json")
        self.contract = build_capacity_contract(self.bundle)

    def test_601_contract_is_deterministic(self):
        self.assertEqual(self.contract, build_capacity_contract(self.bundle))

    def test_602_contract_does_not_claim_unmeasured_slo(self):
        boundary = self.contract["claim_boundary"]
        self.assertFalse(boundary["latency_slo_proven"])
        self.assertFalse(boundary["production_7x24_proven"])

    def test_603_observed_shape_matches_fixture(self):
        shape = self.contract["observed_bundle_shape"]
        self.assertEqual(shape["feature_count"], len(self.bundle["feature_contracts"]))
        self.assertEqual(shape["expert_count"], len(self.bundle["experts"]))

    def test_604_max_configured_batch_passes(self):
        result = assess_workload(
            self.contract,
            batch_size=self.bundle["runtime_limits"]["max_batch"],
            request_bytes_each=1024,
            concurrent_callers=1,
        )
        self.assertEqual(result["status"], "PASS")

    def test_605_batch_over_limit_rejected(self):
        result = assess_workload(
            self.contract,
            batch_size=self.bundle["runtime_limits"]["max_batch"] + 1,
            request_bytes_each=1024,
            concurrent_callers=1,
        )
        self.assertIn("BATCH_LIMIT_EXCEEDED", result["blocking_reasons"])

    def test_606_unproven_concurrency_rejected(self):
        result = assess_workload(self.contract, batch_size=1, request_bytes_each=1024, concurrent_callers=2)
        self.assertIn("CONCURRENCY_NOT_PROVEN_REQUIRES_HOST_ISOLATION", result["blocking_reasons"])

    def test_607_contract_tamper_rejected(self):
        broken = copy.deepcopy(self.contract)
        broken["configured_hard_limits"]["max_batch"] += 1
        with self.assertRaisesRegex(EFSError, "HASH_MISMATCH"):
            assess_workload(broken, batch_size=1, request_bytes_each=1, concurrent_callers=1)

    def test_608_zero_agent_and_token(self):
        result = assess_workload(self.contract, batch_size=1, request_bytes_each=1, concurrent_callers=1)
        self.assertEqual(result["agent_invocations_total"], 0)
        self.assertEqual(result["llm_requests_total"], 0)
        self.assertEqual(result["network_requests_total"], 0)

    def test_609_public_contract_shape_errors_are_controlled(self):
        for malformed in (None, 1, [], "bad"):
            with self.subTest(malformed=type(malformed).__name__):
                with self.assertRaises(EFSError):
                    assess_workload(malformed, batch_size=1, request_bytes_each=1, concurrent_callers=1)

    def test_610_hashed_nested_capacity_shapes_are_still_validated(self):
        for key in ("configured_hard_limits", "deterministic_operation_budget"):
            for malformed in (None, 1, [], {}):
                broken = copy.deepcopy(self.contract)
                broken[key] = malformed
                broken.pop("contract_sha256")
                broken["contract_sha256"] = sha256_hex(broken)
                with self.subTest(key=key, malformed=type(malformed).__name__):
                    with self.assertRaises(EFSError):
                        assess_workload(broken, batch_size=1, request_bytes_each=1, concurrent_callers=1)


if __name__ == "__main__":
    unittest.main()
