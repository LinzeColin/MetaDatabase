from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_foundation_005",
    PROJECT_ROOT / "scripts/verify_foundation_005.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)

import ci_baseline as BASELINE  # noqa: E402


class Foundation005Tests(unittest.TestCase):
    def test_static_task_checks_pass(self) -> None:
        checks = VERIFY.run_checks(
            verify_worktree=False,
            allow_external_main_dirty=False,
        )
        self.assertEqual([item.status for item in checks], ["PASS"] * len(checks))

    def test_run_is_exactly_one_task(self) -> None:
        self.assertEqual(VERIFY.TASK_ID, "TSK.x2n.foundation.005")
        self.assertEqual(VERIFY.RUN_ID, "RUN-X2N-S01-F005")
        self.assertEqual(VERIFY.TASK_BASE_COMMIT, "09d5cdf1993080401f99e023feb03be479baca27")
        self.assertEqual(VERIFY.ORIGIN_CUTOFF, "7fd0768002081f27c070561fa855a08713d1bc00")
        self.assertEqual(
            VERIFY.ALLOWED_CHANGED_PREFIXES,
            (
                "docs/model/",
                "evidence/ci/",
                "packages/test-fixtures/ci/",
                "scripts/ci/",
                "machine/evidence/stage_1/review/",
            ),
        )

    def test_changed_scope_fixture_has_no_critical_false_negative(self) -> None:
        fixture = json.loads(BASELINE.CHANGE_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(len(fixture["cases"]), 8)
        for case in fixture["cases"]:
            result = BASELINE.classify_paths(case["paths"])
            self.assertIs(result["x2n_changed"], case["x2n_changed"], case["id"])
            self.assertIs(result["full_required"], case["full_required"], case["id"])

    def test_seeded_failures_are_detected_without_committed_values(self) -> None:
        report = BASELINE.run_self_test()
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["change_scope_cases"], 8)
        self.assertGreaterEqual(report["seeded_failure_categories"], 8)
        self.assertEqual(report["silent_skips"], 0)
        committed = BASELINE.FAILURE_FIXTURE.read_text(encoding="utf-8")
        self.assertEqual(BASELINE.scan_text(committed, "fixture.json"), [])

    def test_workflow_uses_full_sha_minimal_permissions_and_no_bypass(self) -> None:
        check = VERIFY.validate_workflow()
        self.assertEqual(check.status, "PASS")
        self.assertEqual(check.details["action_uses"], check.details["full_sha_pins"])
        text = BASELINE.WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("continue-on-error", text)
        self.assertNotIn("secrets.", text)
        self.assertNotIn("persist-credentials: true", text)
        self.assertEqual(text.count("fetch-depth: 0"), text.count("actions/checkout@"))

    def test_shared_auth_material_has_no_execution_surface(self) -> None:
        implementation = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                PROJECT_ROOT / "scripts/ci/ci_baseline.py",
                PROJECT_ROOT / "scripts/ci/run_lane.py",
                PROJECT_ROOT / "scripts/verify_foundation_005.py",
            )
        )
        self.assertNotIn("os.environ.copy", implementation)
        self.assertNotIn('"GITHUB_TOKEN"', implementation)
        self.assertNotIn('"GH_TOKEN"', implementation)

    def test_osv_transport_ignores_environment_proxies(self) -> None:
        opener = BASELINE._anonymous_url_opener()
        proxy_handlers = [
            handler for handler in opener.handlers if isinstance(handler, BASELINE.urllib.request.ProxyHandler)
        ]
        self.assertEqual(proxy_handlers, [])

    def test_only_explicit_private_input_skips_are_nonblocking(self) -> None:
        output = "\n".join(
            (
                "test_a ... skipped 'owner-private root is intentionally absent in public CI'",
                "test_b ... skipped 'owner-private root is intentionally absent in public CI'",
                "test_c ... skipped 'private source snapshots are intentionally absent in public CI'",
                "OK (skipped=3)",
            )
        )
        report = BASELINE.validate_unittest_skips(output)
        self.assertEqual(report["explicit_nonblocking_skips"], 3)
        with self.assertRaises(BASELINE.BaselineError):
            BASELINE.validate_unittest_skips(output.replace("private source snapshots", "unexpected input"))

    def test_model_runner_is_contract_only_and_fail_closed(self) -> None:
        report = BASELINE.validate_model_dataset()
        self.assertEqual(report["status"], "PASS_BASELINE_SKELETON")
        self.assertEqual(report["model_calls"], 0)
        self.assertEqual(report["automatic_classification"], "DISABLED_PENDING_ACC.x2n.ai.006")
        self.assertEqual(report["capabilities"]["red_team"], "CONTRACT_PASS_MODEL_NOT_RUN")

    def test_release_candidate_is_allowlisted_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory(prefix="x2n-f005-test-artifact-") as value:
            first = Path(value) / "first.zip"
            second = Path(value) / "second.zip"
            first_report = BASELINE.build_artifact(first)
            second_report = BASELINE.build_artifact(second)
        self.assertEqual(first_report["status"], "PASS")
        self.assertEqual(first_report["runtime_data_files"], 0)
        self.assertEqual(first_report["artifact_sha256"], second_report["artifact_sha256"])

    def test_supply_chain_and_source_scans_are_zero_finding(self) -> None:
        self.assertEqual(BASELINE.scan_source()["finding_count"], 0)
        self.assertEqual(BASELINE.validate_license()["unknown_licenses"], 0)
        sast, sarif = BASELINE.run_sast()
        self.assertEqual(sast["critical_high_findings"], 0)
        self.assertEqual(sarif["runs"][0]["results"], [])

    def test_state_separates_g1_from_remote_and_downstream_execution(self) -> None:
        state = json.loads(VERIFY.TASK_STATE.read_text(encoding="utf-8"))
        self.assertEqual(state["current_stage_gate"], "pass")
        self.assertEqual(state["current_stage_remote_upload"], "authorized_after_g1_pass")
        self.assertEqual(state["remote_ci_execution"], "pending_post_g1_upload")
        self.assertEqual(state["next_run"], "TSK.x2n.skeleton.001")
        historical = json.loads(VERIFY.EVIDENCE.read_text(encoding="utf-8"))
        self.assertEqual(historical["g1"], "NOT_RUN")
        self.assertEqual(historical["remote_github_actions"], "NOT_RUN")
        for field in ("real_account_execution", "platform_calls", "notion_calls", "model_calls", "media_processing"):
            self.assertEqual(state[field], "not_run")


if __name__ == "__main__":
    unittest.main()
