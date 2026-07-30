from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_adapters_006",
    PROJECT_ROOT / "scripts/verify_adapters_006.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)


class Adapters006VerifierTests(unittest.TestCase):
    def test_static_task_checks_pass(self) -> None:
        checks = VERIFY.run_checks(
            verify_worktree=False,
            allow_external_main_dirty=False,
            run_external=False,
        )
        self.assertEqual([item.status for item in checks], ["PASS"] * len(checks))

    def test_run_is_exactly_one_task_and_pinned_by_next_task(self) -> None:
        self.assertEqual(VERIFY.TASK_ID, "TSK.x2n.adapters.006")
        self.assertEqual(VERIFY.RUN_ID, "RUN-X2N-S03-A006")
        self.assertEqual(VERIFY.PHASE, "PH.X2N.3.5")
        self.assertEqual(VERIFY.TASK_BASE_COMMIT, "37ec58cb51d5720bdbe16a67a6e4ea82107c3eb0")
        self.assertEqual(VERIFY.FINAL_COMMIT, "5b6564d289ab3d188015265faf55cceb13fd577a")
        rendered = "\n".join(sorted(VERIFY.ALLOWED_CHANGED_EXACT | set(VERIFY.ALLOWED_CHANGED_PREFIXES)))
        self.assertIn("bilibili_selected", rendered)
        self.assertNotIn("migrations.py", rendered)
        self.assertNotIn("apps/extension/src", rendered)

    def test_predecessor_and_security_surfaces_are_immutable(self) -> None:
        self.assertEqual(VERIFY.PREVIOUS.FINAL_COMMIT, VERIFY.TASK_BASE_COMMIT)
        self.assertEqual(
            VERIFY.PREVIOUS.EVIDENCE.read_bytes(),
            VERIFY._read_blob_at(VERIFY.TASK_BASE_COMMIT, VERIFY.PREVIOUS.EVIDENCE),
        )
        for path in VERIFY.UNCHANGED_SECURITY_SURFACES:
            self.assertEqual(
                VERIFY._read_blob_at(VERIFY.FINAL_COMMIT, path),
                VERIFY._read_blob_at(VERIFY.TASK_BASE_COMMIT, path),
            )

    def test_historical_inputs_and_evidence_are_read_from_final_commit(self) -> None:
        self.assertEqual(
            VERIFY.EVIDENCE.read_bytes(),
            VERIFY._read_blob_at(VERIFY.FINAL_COMMIT, VERIFY.EVIDENCE),
        )
        self.assertEqual(
            VERIFY._load_json_at(VERIFY.FINAL_COMMIT, VERIFY.TASK_STATE)["next_run"],
            "TSK.x2n.adapters.007",
        )

    def test_policy_keeps_real_transport_and_unsupported_lists_disabled(self) -> None:
        policy = VERIFY._load_json(VERIFY.POLICY)
        self.assertFalse(policy["feature_gate"]["production_enabled"])
        self.assertFalse(policy["feature_gate"]["platform_requests"])
        self.assertFalse(policy["transport"]["network_client"])
        self.assertFalse(policy["transport"]["browser_dom_iterator"])
        capability = policy["official_capability"]
        self.assertEqual(capability["required_scope"], "ARC_BASE")
        self.assertEqual(capability["arbitrary_personal_favorites_list"], "unknown_disabled")
        self.assertEqual(capability["arbitrary_personal_likes_list"], "unknown_disabled")

    def test_fixture_is_public_synthetic_and_maps_owner_saved_current(self) -> None:
        fixture = VERIFY._load_json(VERIFY.FIXTURE)
        self.assertTrue(fixture["synthetic"])
        self.assertEqual(len(fixture["cases"]), 38)
        self.assertEqual(len(set(fixture["cases"])), 38)
        mapping = fixture["mapping"]
        self.assertEqual(mapping["selected_manifest_items"], 20)
        self.assertEqual(mapping["expected_identified_percent"], 100)
        self.assertEqual(mapping["expected_saved_current_relations"], 20)
        self.assertEqual(mapping["expected_liked_relations"], 0)
        self.assertEqual(mapping["expected_favorited_relations"], 0)
        for field in (
            "contains_accounts",
            "contains_cookies",
            "contains_credentials",
            "contains_local_absolute_paths",
            "contains_media_urls",
            "contains_private_content",
        ):
            self.assertFalse(fixture[field])

    def test_full_lane_report_is_independently_fail_closed(self) -> None:
        report = {
            "artifact_deterministic": True,
            "artifact_report": {
                "allowlist_findings": 0,
                "member_count": 80,
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
                for gate in VERIFY.PREVIOUS.PREVIOUS.PREVIOUS.PREVIOUS.FULL_LANE_GATES
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
        with tempfile.TemporaryDirectory(prefix="x2n-a006-lane-") as value:
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
        self.assertEqual(evidence["owner_profile_login"], "NOT_RUN")
        self.assertEqual(evidence["owner_canary"], "NOT_RUN")
        self.assertEqual(evidence["real_account_execution"], "NOT_RUN")
        self.assertEqual(evidence["platform_calls"], 0)
        self.assertFalse(evidence["private_content_included"])
        self.assertEqual(evidence["acceptance_input_sha256"], VERIFY._acceptance_input_receipt())


if __name__ == "__main__":
    unittest.main()
