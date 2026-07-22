from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_stage_2_review",
    PROJECT_ROOT / "scripts/verify_stage_2_review.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)


class Stage2ReviewTests(unittest.TestCase):
    def test_review_contract_dag_gate_findings_and_scope_are_consistent(self) -> None:
        checks = (
            VERIFY.validate_review_documents(),
            VERIFY.validate_task_dag_and_state(),
            VERIFY.validate_gate_fact(),
            VERIFY.validate_findings(),
            VERIFY.validate_review_scope(),
        )
        self.assertEqual([check.status for check in checks], ["PASS"] * len(checks))

    def test_taskpack_delta_rejects_new_or_started_stage_3_task(self) -> None:
        current = VERIFY._review_yaml(VERIFY.TASKPACK)
        baseline = VERIFY._yaml_at(VERIFY.REVIEW_BASE_COMMIT, VERIFY.TASKPACK)
        mutated = copy.deepcopy(current)
        mutated["tasks"].append({"id": "TSK.x2n.synthetic.review.escape", "stage": "STG.X2N.3"})
        with self.assertRaises(VERIFY.ReviewError):
            VERIFY._validate_taskpack_review_delta(mutated, baseline)
        mutated = copy.deepcopy(current)
        next(row for row in mutated["tasks"] if row["id"] == "TSK.x2n.adapters.001")["status"] = "in_progress"
        with self.assertRaises(VERIFY.ReviewError):
            VERIFY._validate_taskpack_review_delta(mutated, baseline)

    def test_pr_merge_uses_only_the_skeleton_005_descended_parent(self) -> None:
        merge = "a" * 40
        main_parent = "b" * 40
        review_parent = "c" * 40
        with (
            patch.object(VERIFY, "_git", return_value=f"{merge} {main_parent} {review_parent}"),
            patch.object(VERIFY, "_is_ancestor", side_effect=lambda _ancestor, value: value == review_parent),
        ):
            self.assertEqual(VERIFY._logical_review_head(), review_parent)

    def test_nine_skeleton_receipts_and_s005_final_commit_are_frozen(self) -> None:
        check = VERIFY.validate_skeleton_evidence()
        self.assertEqual(check.status, "PASS")
        self.assertEqual(check.details["frozen_receipts"], 9)
        self.assertEqual(check.details["rewritten_receipts"], 0)
        self.assertEqual(VERIFY.SINK_VERIFIER.FINAL_COMMIT, VERIFY.REVIEW_BASE_COMMIT)
        self.assertEqual(
            VERIFY.SINK_VERIFIER.EVIDENCE.read_bytes(),
            VERIFY.SINK_VERIFIER._read_blob_at(VERIFY.REVIEW_BASE_COMMIT, VERIFY.SINK_VERIFIER.EVIDENCE),
        )

    def test_duplicate_json_and_yaml_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="x2n-g2-duplicates-") as value:
            path = Path(value) / "duplicate.json"
            path.write_text('{"status":"PASS","status":"FAIL"}\n', encoding="utf-8")
            with self.assertRaises(VERIFY.ReviewError):
                VERIFY._load_json(path)
        with self.assertRaises(VERIFY.ReviewError):
            VERIFY._load_yaml_text("status: PASS\nstatus: FAIL\n", "duplicate.yaml")

    def test_toolchain_identity_is_exact_and_python_313_fails_closed(self) -> None:
        expected = VERIFY._load_json(VERIFY.CI_POLICY)["toolchain"]
        actual = {
            "python": "3.12.13",
            "node": "24.18.0",
            "npm": "11.16.0",
            "uv": "0.11.28",
            "ruff": "0.15.22",
            "coverage": "7.15.2",
            "pyyaml": "6.0.3",
        }
        VERIFY.LANE._validate_toolchain_versions(expected, actual)
        actual["python"] = "3.13.14"
        with self.assertRaises(VERIFY.LANE.LaneError):
            VERIFY.LANE._validate_toolchain_versions(expected, actual)

    def test_g2_oracle_rejects_a_duplicate_without_external_execution(self) -> None:
        receipt = {"bytes": 1, "sha256": "a" * 64}
        platform_details = {
            "service_worker_restarts_per_platform": 100,
            "action_before_grant_rejections_per_platform": 2,
            "platform_calls": 0,
            "owner_canary": "NOT_RUN",
        }
        for name in ("xhs", "douyin", "bilibili", "kuaishou", "weibo", "taobao"):
            platform_details[f"{name}_screenshot"] = receipt
            platform_details[f"{name}_trace"] = receipt
        platform = SimpleNamespace(status="PASS", details=platform_details)
        media = SimpleNamespace(
            status="PASS",
            details={"scanner_findings": 0, "cleanup_cases": 8, "active_lease_misdeletes": 0},
        )
        orchestration = SimpleNamespace(
            status="PASS",
            details={"duplicate_entities": 0, "stuck_runs": 0, "broken_provenance_traces": 0},
        )
        sinks = SimpleNamespace(
            status="PASS",
            details={"duplicate_pages": 0, "partial_files": 0, "unit_tests": 17, "notion_real_api_calls": 0},
        )
        with (
            patch.object(VERIFY.PLATFORM_VERIFIER, "validate_execution", return_value=platform),
            patch.object(VERIFY.MEDIA_VERIFIER, "validate_execution", return_value=media),
            patch.object(VERIFY.ORCHESTRATOR_VERIFIER, "validate_execution", return_value=orchestration),
            patch.object(VERIFY.SINK_VERIFIER, "validate_execution", return_value=sinks),
        ):
            self.assertEqual(VERIFY.validate_g2_acceptance().status, "PASS")
            orchestration.details["duplicate_entities"] = 1
            with self.assertRaises(VERIFY.ReviewError):
                VERIFY.validate_g2_acceptance()

    def test_g2_does_not_overstate_remote_formal_or_real_execution(self) -> None:
        fact = json.loads(VERIFY.G2_FACT.read_text(encoding="utf-8"))
        self.assertEqual(fact["gate_status"], "pass")
        self.assertEqual(fact["assurance_scope"], "project_native_local_developer_gate")
        self.assertEqual(fact["remote_ci_execution"], "pending_post_g2_upload")
        self.assertEqual(
            fact["formal_verifier_release_candidate"], "blocked_requirement_gap_missing_canonical_manifest"
        )
        self.assertFalse(fact["stage_3_authorized"])
        self.assertFalse(fact["public_release_authorized"])
        for field in ("real_account_execution", "platform_calls", "model_calls", "media_processing"):
            self.assertEqual(fact[field], "not_run")

    def test_software_lane_is_stage_neutral_and_outage_oracle_is_named(self) -> None:
        lane = (PROJECT_ROOT / "scripts/ci/run_lane.py").read_text(encoding="utf-8")
        sinks = VERIFY.SINK_VERIFIER._read_blob_at(
            VERIFY.SINK_VERIFIER.FINAL_COMMIT,
            VERIFY.SINK_VERIFIER.SINK_TEST,
        ).decode("utf-8")
        self.assertNotIn('"g1": "NOT_RUN"', lane)
        self.assertIn('"stage_gate_evaluation": "NOT_PERFORMED_BY_SOFTWARE_LANE"', lane)
        self.assertIn("test_one_hour_notion_outage_does_not_block_canonical_or_markdown", sinks)

    def test_history_scanner_detects_seeded_sensitive_shapes(self) -> None:
        secret = "github" + "_pat_" + "A" * 24
        local_path = "/" + "Users/example/private/item"
        cdn = "https://" + "video.ali" + "cdn.example/item"
        findings = VERIFY.scan_text("\n".join((secret, local_path, cdn)), "synthetic.txt")
        self.assertEqual(
            {finding.code for finding in findings},
            {"cdn.platform_media_url", "private.local_absolute_path", "secret.github_token_shape"},
        )


if __name__ == "__main__":
    unittest.main()
