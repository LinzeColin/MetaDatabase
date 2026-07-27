from __future__ import annotations

import copy
import json
import socket
import unittest
from pathlib import Path
from unittest import mock

from equity_foresight_signal import (
    build_business_baseline_matrix,
    build_host_status_payload,
    build_recovery_plan,
    validate_business_baseline_matrix,
)
from equity_foresight_signal.canonical import sha256_hex
from equity_foresight_signal.errors import EFSError
from tests.test_runtime_operations import failed_outcome_report

ROOT = Path(__file__).resolve().parents[1]


def load(name: str) -> dict:
    return json.loads((ROOT / "fixtures" / name).read_text(encoding="utf-8"))


def rebuild_bundle(bundle: dict) -> dict:
    value = copy.deepcopy(bundle)
    value.pop("payload_sha256", None)
    value["payload_sha256"] = sha256_hex(value)
    return value


class HostContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = load("bundle.json")
        self.as_of = "2026-07-24T21:00:00Z"

    def test_401_status_payload_is_deterministic(self):
        first = build_host_status_payload(as_of=self.as_of, bundle=self.bundle)
        second = build_host_status_payload(as_of=self.as_of, bundle=self.bundle)
        self.assertEqual(first, second)
        self.assertEqual(first["overall_status"], "HEALTHY")
        self.assertEqual(first["payload_sha256"], sha256_hex({k: v for k, v in first.items() if k != "payload_sha256"}))

    def test_402_runtime_only_status(self):
        result = build_host_status_payload(as_of=self.as_of)
        self.assertEqual(result["overall_status"], "HEALTHY_RUNTIME_ONLY")
        self.assertEqual(result["bundle_state"], "NOT_PROVIDED")

    def test_403_host_owns_transport_and_persistence(self):
        result = build_host_status_payload(as_of=self.as_of, bundle=self.bundle)
        self.assertTrue(result["host_transport_required"])
        self.assertFalse(result["self_persistence"])
        forbidden = {"token", "cookie", "password", "private_key", "api_key"}
        def walk(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    self.assertNotIn(key.lower(), forbidden)
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)
        walk(result)

    def test_404_status_has_zero_agent_token_network(self):
        result = build_host_status_payload(as_of=self.as_of, bundle=self.bundle)
        for key in (
            "agent_invocations_total", "llm_requests_total", "llm_input_tokens_total",
            "llm_output_tokens_total", "network_requests_total",
        ):
            self.assertEqual(result[key], 0)

    def test_405_status_runs_with_network_blocked(self):
        with mock.patch.object(socket, "socket", side_effect=AssertionError("network forbidden")):
            result = build_host_status_payload(as_of=self.as_of, bundle=self.bundle)
        self.assertEqual(result["overall_status"], "HEALTHY")

    def test_406_invalid_as_of_rejected(self):
        with self.assertRaises(EFSError):
            build_host_status_payload(as_of="now", bundle=self.bundle)

    def test_407_missing_candidate_keeps_lkg(self):
        plan = build_recovery_plan(as_of=self.as_of, lkg=self.bundle, failure_code="DATA_STALE")
        self.assertEqual(plan["decision"], "KEEP_LKG")
        self.assertFalse(plan["automatic_execution_permitted"])
        self.assertFalse(plan["state_mutation_performed"])

    def test_408_bad_candidate_is_rejected_without_mutation(self):
        candidate = copy.deepcopy(self.bundle)
        candidate["payload_sha256"] = "0" * 64
        plan = build_recovery_plan(
            as_of=self.as_of, lkg=self.bundle, candidate=candidate, failure_code="CANDIDATE_INVALID"
        )
        self.assertEqual(plan["decision"], "REJECT_CANDIDATE_KEEP_LKG")
        self.assertFalse(plan["state_mutation_performed"])

    def test_409_unhealthy_lkg_requires_host_restore(self):
        expired = copy.deepcopy(self.bundle)
        expired["expires_at"] = "2026-01-01T00:00:00Z"
        expired = rebuild_bundle(expired)
        plan = build_recovery_plan(
            as_of=self.as_of, lkg=expired, candidate=None, failure_code="LKG_EXPIRED"
        )
        self.assertEqual(plan["decision"], "HOST_RESTORE_REQUIRED")
        self.assertIn("LKG_NOT_HEALTHY", plan["blocking_reasons"])

    def test_410_recovery_plan_zero_agent_token_network(self):
        with mock.patch.object(socket, "socket", side_effect=AssertionError("network forbidden")):
            plan = build_recovery_plan(
                as_of=self.as_of, lkg=self.bundle, candidate=self.bundle, failure_code="TEST_FAILURE"
            )
        for key in (
            "agent_invocations_total", "llm_requests_total", "llm_input_tokens_total",
            "llm_output_tokens_total", "network_requests_total",
        ):
            self.assertEqual(plan[key], 0)

    def test_411_failure_code_is_bounded(self):
        with self.assertRaises(EFSError):
            build_recovery_plan(as_of=self.as_of, lkg=self.bundle, failure_code="x" * 129)

    def test_412_business_baseline_matrix_is_hash_bound_and_white_box(self):
        result = build_host_status_payload(as_of=self.as_of, bundle=self.bundle)
        matrix = result["business_baseline_matrix"]
        self.assertEqual(matrix["minimum_host_view"], "MATRIX_TABLE")
        self.assertEqual(matrix["status_endpoint"], "status.linzezhang.com")
        self.assertEqual(result["business_baseline_matrix_sha256"], matrix["matrix_sha256"])
        self.assertEqual(
            matrix["matrix_sha256"],
            sha256_hex({key: value for key, value in matrix.items() if key != "matrix_sha256"}),
        )
        rows = matrix["rows"]
        ids = [row["business_line_id"] for row in rows]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, [
            "BL-01-DATA-EVIDENCE",
            "BL-02-FORECAST",
            "BL-03-OUTCOME",
            "BL-04-LIFECYCLE",
            "BL-05-STATUS",
        ])
        for row in rows:
            self.assertTrue(row["stage"])
            self.assertTrue(row["phase"])
            self.assertTrue(row["status"])
            self.assertIsInstance(row["depends_on"], list)
            self.assertIsInstance(row["downstream"], list)
            self.assertIsInstance(row["coupling_controls"], list)
            self.assertTrue(row["next_action"])

    def test_413_business_matrix_dependencies_are_acyclic_and_known(self):
        matrix = build_business_baseline_matrix(as_of=self.as_of, bundle=self.bundle)
        report = validate_business_baseline_matrix(matrix)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["topology_status"], "ACYCLIC")
        self.assertEqual(report["orphan_count"], 0)
        self.assertEqual(matrix["summary"]["line_count"], 5)
        self.assertEqual(matrix["summary"]["edge_count"], 7)
        rows = {row["business_line_id"]: row for row in matrix["rows"]}
        self.assertEqual(
            rows["BL-05-STATUS"]["depends_on"],
            [
                "BL-01-DATA-EVIDENCE",
                "BL-02-FORECAST",
                "BL-03-OUTCOME",
                "BL-04-LIFECYCLE",
            ],
        )

    def test_414_invalid_bundle_is_visible_as_blocked_not_hidden(self):
        broken = copy.deepcopy(self.bundle)
        broken["payload_sha256"] = "0" * 64
        matrix = build_host_status_payload(as_of=self.as_of, bundle=broken)["business_baseline_matrix"]
        rows = {row["business_line_id"]: row for row in matrix["rows"]}
        self.assertEqual(rows["BL-01-DATA-EVIDENCE"]["status"], "BLOCKED")
        self.assertEqual(rows["BL-02-FORECAST"]["status"], "BLOCKED_BY_UPSTREAM")
        self.assertEqual(rows["BL-05-STATUS"]["status"], "READY_FOR_HOST_TRANSPORT")
        self.assertFalse(matrix["self_network_transport"])
        self.assertFalse(matrix["self_persistence"])

    def test_415_business_matrix_tamper_and_cycle_fail_closed(self):
        matrix = build_business_baseline_matrix(as_of=self.as_of, bundle=self.bundle)
        tampered = copy.deepcopy(matrix)
        tampered["summary"]["line_count"] = 999
        tampered.pop("matrix_sha256")
        tampered["matrix_sha256"] = sha256_hex(tampered)
        with self.assertRaisesRegex(EFSError, "summary mismatch"):
            validate_business_baseline_matrix(tampered)

        cyclic = copy.deepcopy(matrix)
        cyclic["edges"].append({
            "from": "BL-05-STATUS",
            "to": "BL-01-DATA-EVIDENCE",
            "relation": "INVALID_CYCLE",
        })
        cyclic["rows"][0]["depends_on"].append("BL-05-STATUS")
        cyclic["rows"][4]["downstream"].append("BL-01-DATA-EVIDENCE")
        cyclic.pop("matrix_sha256")
        cyclic["matrix_sha256"] = sha256_hex(cyclic)
        with self.assertRaisesRegex(EFSError, "cycle"):
            validate_business_baseline_matrix(cyclic)

    def test_416_business_matrix_snapshot_contract_is_host_owned_and_zero_token(self):
        matrix = build_business_baseline_matrix(as_of=self.as_of, bundle=self.bundle)
        self.assertEqual(matrix["status_snapshot_key"], "business_baselines.equity_foresight_signal")
        self.assertEqual(matrix["minimum_host_view"], "MATRIX_TABLE")
        self.assertFalse(matrix["self_network_transport"])
        self.assertFalse(matrix["self_persistence"])
        for key in (
            "agent_invocations_total", "llm_requests_total", "llm_input_tokens_total",
            "llm_output_tokens_total", "network_requests_total",
        ):
            self.assertEqual(matrix[key], 0)

    def test_417_direct_matrix_builder_rejects_unbound_outcome(self):
        outcome = failed_outcome_report(self.bundle)
        outcome["subject_model_set_sha256"] = "0" * 64
        outcome.pop("report_sha256")
        outcome["report_sha256"] = sha256_hex(outcome)
        with self.assertRaisesRegex(EFSError, "does not belong to the supplied bundle"):
            build_business_baseline_matrix(
                as_of=self.as_of,
                bundle=self.bundle,
                outcome_report=outcome,
            )


if __name__ == "__main__":
    unittest.main()
