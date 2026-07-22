from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_adapters_005",
    PROJECT_ROOT / "scripts/verify_adapters_005.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)


class Adapters005VerifierTests(unittest.TestCase):
    def test_static_task_checks_pass(self) -> None:
        checks = VERIFY.run_checks(
            verify_worktree=False,
            allow_external_main_dirty=False,
            run_external=False,
        )
        self.assertEqual([item.status for item in checks], ["PASS"] * len(checks))

    def test_run_is_exactly_one_unpinned_task(self) -> None:
        self.assertEqual(VERIFY.TASK_ID, "TSK.x2n.adapters.005")
        self.assertEqual(VERIFY.RUN_ID, "RUN-X2N-S03-A005")
        self.assertEqual(VERIFY.PHASE, "PH.X2N.3.9")
        self.assertEqual(VERIFY.TASK_BASE_COMMIT, "8c6442a251f73e645e292a4e77dd03448d153b64")
        self.assertFalse(hasattr(VERIFY, "FINAL_COMMIT"))
        rendered = "\n".join(sorted(VERIFY.ALLOWED_CHANGED_EXACT | set(VERIFY.ALLOWED_CHANGED_PREFIXES)))
        self.assertIn("relation_reconciliation", rendered)
        self.assertNotIn("migrations.py", rendered)
        self.assertNotIn("apps/extension/src/", rendered)

    def test_predecessor_and_security_surfaces_are_immutable(self) -> None:
        self.assertEqual(VERIFY.PREVIOUS.FINAL_COMMIT, VERIFY.TASK_BASE_COMMIT)
        self.assertEqual(
            VERIFY.PREVIOUS.EVIDENCE.read_bytes(),
            VERIFY._read_blob_at(VERIFY.TASK_BASE_COMMIT, VERIFY.PREVIOUS.EVIDENCE),
        )
        for path in VERIFY.UNCHANGED_SECURITY_SURFACES:
            self.assertEqual(path.read_bytes(), VERIFY._read_blob_at(VERIFY.TASK_BASE_COMMIT, path))

    def test_policy_only_allows_proven_xhs_full_scans(self) -> None:
        policy = VERIFY._load_json(VERIFY.POLICY)
        sources = policy["authoritative_sources"]
        self.assertTrue(sources["xhs_favorites"]["full_scan_permitted"])
        self.assertTrue(sources["xhs_likes"]["full_scan_permitted"])
        for source in (
            "douyin_upstream",
            "bilibili_selected_collection",
            "kuaishou_selected_collection",
            "weibo_selected_collection",
            "taobao_selected_collection",
        ):
            self.assertFalse(sources[source]["full_scan_permitted"])
        self.assertFalse(policy["full_scan_proof"]["empty_scan_permitted"])
        self.assertTrue(policy["full_scan_proof"]["distinct_source_run_required"])
        self.assertFalse(policy["state_machine"]["automatic_removed_transition"])
        self.assertFalse(policy["scope"]["physical_delete"])

    def test_fixture_covers_state_idempotency_and_kill_without_private_data(self) -> None:
        fixture = VERIFY._load_json(VERIFY.FIXTURE)
        self.assertTrue(fixture["synthetic"])
        self.assertEqual(len(fixture["cases"]), 40)
        self.assertEqual(len(set(fixture["cases"])), 40)
        self.assertEqual(fixture["state_machine"]["expected_candidates_after_second_complete_missing_scan"], 10)
        self.assertEqual(fixture["idempotency"]["input_items"], 80)
        self.assertEqual(fixture["idempotency"]["concurrent_duplicate_messages"], 100)
        self.assertEqual(fixture["chaos"]["kill_runs"], 50)
        self.assertEqual(fixture["owner_alpha_tooling"]["execution"], "NOT_RUN")
        for field in (
            "contains_accounts",
            "contains_cookies",
            "contains_credentials",
            "contains_local_absolute_paths",
            "contains_media_urls",
            "contains_private_content",
        ):
            self.assertFalse(fixture[field])

    def test_implementation_has_no_delete_or_network_client(self) -> None:
        source = VERIFY.COMPANION_SOURCE.read_text(encoding="utf-8")
        self.assertIn("RelationStatus.TOMBSTONE_CANDIDATE", source)
        self.assertIn("last_source_checkpoint_at", source)
        self.assertNotIn("DELETE FROM user_relation", source)
        self.assertNotIn("DELETE FROM content", source)
        self.assertNotIn("requests.", source)
        self.assertNotIn("httpx.", source)

    def test_full_lane_report_is_independently_fail_closed(self) -> None:
        module = VERIFY
        while not hasattr(module, "FULL_LANE_GATES"):
            module = module.PREVIOUS
        gates = module.FULL_LANE_GATES
        report = {
            "artifact_deterministic": True,
            "artifact_report": {
                "allowlist_findings": 0,
                "member_count": 89,
                "runtime_data_files": 0,
                "status": "PASS",
            },
            "blocking_commands": 12,
            "blocking_executions": 24,
            "blocking_failures": 0,
            "blocking_repetitions": 2,
            "blocking_results": [
                {
                    "blocking": True,
                    "gate": gate,
                    "label": f"{gate}_r{repetition}",
                    "repetition": repetition,
                    "status": "PASS",
                }
                for repetition in (1, 2)
                for gate in gates
            ],
            "coverage": {"branch_mode": True, "overall_combined_percent": 78.0, "status": "PASS"},
            "explicit_nonblocking_skips": 6,
            "flaky_blocking_tests": 0,
            "lane": "full",
            "model_calls": 0,
            "osv": {
                "critical_high_unresolved": 0,
                "dependencies_queried": 33,
                "status": "PASS",
                "vulnerabilities_reported": 0,
            },
            "platform_calls": 0,
            "real_accounts": 0,
            "silent_blocking_skips": 0,
            "status": "PASS",
        }
        with tempfile.TemporaryDirectory(prefix="x2n-a005-lane-") as value:
            path = Path(value) / "software-lane.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(VERIFY.validate_full_lane_report(path).status, "PASS")
            report["platform_calls"] = 1
            path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesRegex(VERIFY.VerificationError, "forbidden external surface"):
                VERIFY.validate_full_lane_report(path)

    def test_evidence_never_claims_owner_or_real_execution(self) -> None:
        if not VERIFY.EVIDENCE.is_file():
            self.assertFalse(VERIFY.EVIDENCE.exists())
            return
        evidence = json.loads(VERIFY.EVIDENCE.read_text(encoding="utf-8"))
        self.assertEqual(evidence["owner_alpha"], "NOT_RUN")
        self.assertEqual(evidence["owner_profile_login"], "NOT_RUN")
        self.assertEqual(evidence["real_account_execution"], "NOT_RUN")
        self.assertEqual(evidence["platform_calls"], 0)
        self.assertFalse(evidence["owner_alpha_private_manifest_created"])
        self.assertFalse(evidence["private_content_included"])
        self.assertEqual(evidence["task_metrics"]["synthetic_chaos_manifest_residuals"], 0)
        self.assertEqual(evidence["acceptance_input_sha256"], VERIFY._acceptance_input_receipt())


if __name__ == "__main__":
    unittest.main()
