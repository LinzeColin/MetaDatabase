from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from equity_foresight_signal import (
    audit_runtime_source,
    build_business_baseline_matrix,
    build_host_status_payload,
    evaluate_oos_records,
)
from equity_foresight_signal.canonical import sha256_hex
from equity_foresight_signal.errors import EFSError

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "equity_foresight_signal"


def failed_outcome_report(bundle: dict) -> dict:
    policy = {
        "schema": "efs.validation_policy.v1",
        "policy_id": "status_adapter_failed_outcome_v1",
        "evaluation_role": "OOS",
        "evaluation_as_of": "2026-07-25T00:00:00Z",
        "horizon": 20,
        "hurdle": "0",
        "calibration_bins": 10,
        "minimum_records": 20,
        "minimum_clusters": 2,
        "minimum_brier_skill": "0.05",
        "minimum_auc": "0.55",
        "maximum_ece": "0.15",
        "minimum_interval_coverage": "0.70",
        "maximum_interval_coverage": "1.00",
        "maximum_timing_brier": "0.20",
        "cost_stress_multiplier": "2",
        "minimum_mean_stressed_return": "0.001",
        "maximum_monotonicity_violations": 2,
        "subject_model_set_sha256": bundle["model_set_sha256"],
        "trial_manifest_sha256": sha256_hex({"trial_manifest": "status_fixture"}),
        "dataset_snapshot_sha256": sha256_hex({"dataset": "status_fixture"}),
    }
    policy["policy_sha256"] = sha256_hex(policy)
    start = datetime(2022, 1, 1, tzinfo=timezone.utc)
    records = []
    for index in range(20):
        positive = index % 2 == 0
        forecast = start + timedelta(days=index * 25)
        net = "0.029" if positive else "-0.016"
        event = "UP" if positive else "DOWN"
        record = {
            "schema": "efs.oos_forecast_record.v1",
            "record_id": f"status_oos_{index:03d}",
            "forecast_as_of": forecast.isoformat().replace("+00:00", "Z"),
            "label_matured_at": (forecast + timedelta(days=21)).isoformat().replace("+00:00", "Z"),
            "instrument_id": f"FIGI:STATUS{index % 4:02d}",
            "horizon": 20,
            "cluster_id": f"cluster_{index % 2}",
            "prob_up": "0.10" if positive else "0.90",
            "baseline_prob": "0.50",
            "gross_return": "0.03" if positive else "-0.015",
            "cost_return": "0.001",
            "p10": "-0.05",
            "p50": net,
            "p90": "0.06",
            "timing_up": "0.90" if positive else "0.05",
            "timing_down": "0.05" if positive else "0.90",
            "timing_timeout": "0.05",
            "realized_event": event,
        }
        record["source_record_sha256"] = sha256_hex(record)
        records.append(record)
    return evaluate_oos_records(records, policy)


class RuntimeAuditTests(unittest.TestCase):
    def test_401_current_runtime_static_audit_passes(self):
        report = audit_runtime_source(PACKAGE)
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["zero_agent_static_claim"])
        self.assertTrue(report["zero_llm_token_static_claim"])
        self.assertEqual(report["agent_llm_imports"], [])
        self.assertEqual(report["network_imports"], [])
        self.assertEqual(report["process_imports"], [])
        self.assertTrue(report["zero_local_persistence_static_claim"])
        self.assertTrue(report["zero_macos_launchd_static_claim"])
        self.assertEqual(report["persistence_imports"], [])
        self.assertEqual(report["local_persistence_calls"], [])
        self.assertEqual(report["local_environment_dependencies"], [])

    def test_402_audit_is_deterministic(self):
        self.assertEqual(audit_runtime_source(PACKAGE), audit_runtime_source(PACKAGE))

    def test_403_openai_import_is_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bad.py").write_text("import openai\n", encoding="utf-8")
            report = audit_runtime_source(root)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("AGENT_OR_LLM_IMPORT_PRESENT", report["blocking_reasons"])

    def test_404_socket_call_is_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bad.py").write_text("import socket\nsocket.socket()\n", encoding="utf-8")
            report = audit_runtime_source(root)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("NETWORK_IMPORT_PRESENT", report["blocking_reasons"])
        self.assertIn("FORBIDDEN_RUNTIME_CALL_PRESENT", report["blocking_reasons"])

    def test_405_pickle_loader_is_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bad.py").write_text("import pickle\npickle.loads(b'x')\n", encoding="utf-8")
            report = audit_runtime_source(root)
        self.assertIn("UNSAFE_MODEL_LOADER_PRESENT", report["blocking_reasons"])

    def test_406_static_audit_does_not_claim_os_proof(self):
        report = audit_runtime_source(PACKAGE)
        self.assertEqual(report["os_network_isolation_status"], "NOT_PROVEN_BY_STATIC_AUDIT")
        self.assertEqual(report["os_process_isolation_status"], "NOT_PROVEN_BY_STATIC_AUDIT")

    def test_413_write_mode_open_is_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bad.py").write_text("open('state.json', 'w').write('x')\n", encoding="utf-8")
            report = audit_runtime_source(root)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("LOCAL_PERSISTENCE_CALL_PRESENT", report["blocking_reasons"])
        self.assertIn("open(write_mode)", report["local_persistence_calls"])

    def test_414_persistence_module_is_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bad.py").write_text("import sqlite3\n", encoding="utf-8")
            report = audit_runtime_source(root)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("LOCAL_PERSISTENCE_IMPORT_PRESENT", report["blocking_reasons"])
        self.assertIn("sqlite3", report["persistence_imports"])

    def test_415_home_dependency_is_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bad.py").write_text("import os\nvalue=os.getenv('HOME')\n", encoding="utf-8")
            report = audit_runtime_source(root)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("LOCAL_HOME_OR_XDG_DEPENDENCY_PRESENT", report["blocking_reasons"])

    def test_416_launchctl_process_invocation_is_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bad.py").write_text(
                "import subprocess\nsubprocess.run(['launchctl'])\n",
                encoding="utf-8",
            )
            report = audit_runtime_source(root)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("PROCESS_IMPORT_PRESENT", report["blocking_reasons"])
        self.assertIn("FORBIDDEN_RUNTIME_CALL_PRESENT", report["blocking_reasons"])
        self.assertFalse(report["zero_macos_launchd_static_claim"])


class HostStatusAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = json.loads((ROOT / "fixtures" / "bundle.json").read_text(encoding="utf-8"))

    def test_407_healthy_without_outcome_is_research_only(self):
        payload = build_host_status_payload(as_of="2026-07-24T21:00:00Z", bundle=self.bundle)
        self.assertEqual(payload["overall_status"], "HEALTHY")
        self.assertEqual(payload["capability_state"], "RESEARCH_ONLY")
        self.assertFalse(payload["self_network_transport"])
        self.assertFalse(payload["self_persistence"])

    def test_408_invalid_bundle_health_is_red_and_abstain(self):
        broken = dict(self.bundle)
        broken["payload_sha256"] = "0" * 64
        payload = build_host_status_payload(as_of="2026-07-24T21:00:00Z", bundle=broken)
        self.assertEqual(payload["overall_status"], "UNHEALTHY")
        self.assertEqual(payload["capability_state"], "ABSTAIN")
        self.assertEqual(payload["recovery_directive"], "KEEP_LKG_AND_ABSTAIN")

    def test_409_failed_outcome_keeps_lkg_non_blocking(self):
        outcome = failed_outcome_report(self.bundle)
        payload = build_host_status_payload(as_of="2026-07-24T21:00:00Z", bundle=self.bundle, outcome_report=outcome)
        self.assertEqual(payload["capability_state"], "SHADOW_ONLY")
        self.assertEqual(payload["recovery_directive"], "KEEP_LKG_AND_CONTINUE_NON_BLOCKING_VALIDATION")

    def test_410_status_payload_is_deterministic_and_zero_token(self):
        first = build_host_status_payload(as_of="2026-07-24T21:00:00Z", bundle=self.bundle)
        second = build_host_status_payload(as_of="2026-07-24T21:00:00Z", bundle=self.bundle)
        self.assertEqual(first, second)
        self.assertEqual(first["agent_invocations_total"], 0)
        self.assertEqual(first["llm_requests_total"], 0)
        self.assertEqual(first["network_requests_total"], 0)

    def test_411_invalid_outcome_type_is_rejected(self):
        with self.assertRaisesRegex(EFSError, "CONTRACT_INVALID"):
            build_host_status_payload(as_of="2026-07-24T21:00:00Z", bundle=self.bundle, outcome_report="bad")

    def test_412_unhashable_outcome_status_is_rejected_as_contract_error(self):
        outcome = {"schema": "efs.validation_report.v1", "overall_status": {"invalid": True}}
        outcome["report_sha256"] = sha256_hex(outcome)
        with self.assertRaisesRegex(EFSError, "CONTRACT_INVALID"):
            build_host_status_payload(
                as_of="2026-07-24T21:00:00Z",
                bundle=self.bundle,
                outcome_report=outcome,
            )

    def test_413_matrix_only_api_rejects_outcome_from_another_model_set(self):
        outcome = failed_outcome_report(self.bundle)
        outcome["subject_model_set_sha256"] = "0" * 64
        outcome.pop("report_sha256")
        outcome["report_sha256"] = sha256_hex(outcome)
        with self.assertRaisesRegex(EFSError, "does not belong"):
            build_business_baseline_matrix(
                as_of="2026-07-24T21:00:00Z",
                bundle=self.bundle,
                outcome_report=outcome,
            )


class RuntimeDependencyBoundaryTests(unittest.TestCase):
    def test_790_formal_release_has_no_external_runtime_import(self):
        report = audit_runtime_source(ROOT / "equity_foresight_signal")
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["external_runtime_imports"], [])
        self.assertEqual(report["undeclared_external_imports"], [])
        self.assertEqual(report["dependency_boundary"]["research_shadow_core"], "PYTHON_STANDARD_LIBRARY_ONLY")

    def test_791_undeclared_external_runtime_dependency_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / "fixture_runtime"
            package.mkdir()
            (package / "core.py").write_text("import pandas\n", encoding="utf-8")
            report = audit_runtime_source(package)
            self.assertEqual(report["status"], "FAIL")
            self.assertIn("pandas", report["undeclared_external_imports"])
            self.assertIn("UNDECLARED_RUNTIME_DEPENDENCY_PRESENT", report["blocking_reasons"])


if __name__ == "__main__":
    unittest.main()
