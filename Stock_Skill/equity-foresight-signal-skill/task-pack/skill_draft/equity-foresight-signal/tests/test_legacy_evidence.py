from __future__ import annotations

import json
import unittest
from pathlib import Path

from equity_foresight_signal.canonical import sha256_hex
from equity_foresight_signal.errors import EFSError
from equity_foresight_signal.legacy_evidence import build_legacy_backtest_receipt

ROOT = Path(__file__).resolve().parents[1]
PRIOR = Path("/mnt/data/efs_prior_backtest/FPMT_readonly_discovery_2026-07-22")


def small_inputs() -> tuple[bytes, bytes, bytes]:
    header = "model,n,start,end,positive_rate,mean_predicted,brier,log_loss,roc_auc,ece_10_equal_frequency,calibration_slope,calibration_intercept,horizon\n"
    rows = []
    for horizon, base, candidate in ((5, "0.24", "0.25"), (20, "0.22", "0.23"), (60, "0.20", "0.21")):
        rows.append(f"rolling_base_rate,100,2000-01-01,2020-01-01,0.6,0.6,{base},0.6,0.51,0.1,1,0,{horizon}\n")
        rows.append(f"regularized_logistic_online_platt,100,2000-01-01,2020-01-01,0.6,0.6,{candidate},0.7,0.49,0.1,1,0,{horizon}\n")
    manifest = {"data": {"start": "2000-01-01", "end": "2020-01-01", "rows": 100}, "design": {"round_trip_cost": 0.001}}
    return (header + "".join(rows)).encode(), json.dumps(manifest).encode(), b"negative report"


class LegacyEvidenceTests(unittest.TestCase):
    def test_501_negative_receipt_is_deterministic_and_shadow_only(self):
        metrics, manifest, report = small_inputs()
        first = build_legacy_backtest_receipt(model_metrics_csv=metrics, run_manifest_json=manifest, report_markdown=report, source_label="fixture")
        second = build_legacy_backtest_receipt(model_metrics_csv=metrics, run_manifest_json=manifest, report_markdown=report, source_label="fixture")
        self.assertEqual(first, second)
        self.assertEqual(first["overall_status"], "FAIL")
        self.assertEqual(first["capability_limit"], "SHADOW_ONLY")
        self.assertFalse(first["promotion_evidence_eligible"])
        self.assertTrue(all(not row["passed_frozen_null_baseline"] for row in first["horizon_results"]))
        payload = dict(first)
        digest = payload.pop("receipt_sha256")
        self.assertEqual(digest, sha256_hex(payload))

    def test_502_positive_horizon_cannot_be_mislabelled_as_frozen_negative(self):
        metrics, manifest, report = small_inputs()
        metrics = metrics.replace(b"regularized_logistic_online_platt,100,2000-01-01,2020-01-01,0.6,0.6,0.25", b"regularized_logistic_online_platt,100,2000-01-01,2020-01-01,0.6,0.6,0.19", 1)
        with self.assertRaisesRegex(EFSError, "CONTRACT_INVALID"):
            build_legacy_backtest_receipt(model_metrics_csv=metrics, run_manifest_json=manifest, report_markdown=report, source_label="fixture")

    def test_503_missing_model_pair_is_rejected(self):
        metrics, manifest, report = small_inputs()
        lines = metrics.decode().splitlines()
        metrics = ("\n".join(line for line in lines if not line.endswith(",60") or line.startswith("rolling_base_rate")) + "\n").encode()
        with self.assertRaisesRegex(EFSError, "CONTRACT_INVALID"):
            build_legacy_backtest_receipt(model_metrics_csv=metrics, run_manifest_json=manifest, report_markdown=report, source_label="fixture")

    @unittest.skipUnless(PRIOR.exists(), "prior evidence package is not present in this runtime")
    def test_504_real_prior_receipt_matches_frozen_negative_facts(self):
        receipt = build_legacy_backtest_receipt(
            model_metrics_csv=(PRIOR / "backtest/results/model_metrics.csv").read_bytes(),
            run_manifest_json=(PRIOR / "backtest/results/run_manifest.json").read_bytes(),
            report_markdown=(PRIOR / "BACKTEST_REPORT.md").read_bytes(),
            source_label="FPMT_readonly_discovery_2026-07-22",
        )
        self.assertEqual([row["sample_count"] for row in receipt["horizon_results"]], [4238, 4193, 4073])
        self.assertEqual([row["brier_skill"] for row in receipt["horizon_results"]], ["-0.00273438", "-0.00259432", "-0.04932761"])
        self.assertEqual(receipt["agent_invocations_total"], 0)
        self.assertEqual(receipt["llm_requests_total"], 0)


if __name__ == "__main__":
    unittest.main()
