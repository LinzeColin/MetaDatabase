from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_foundation_003",
    PROJECT_ROOT / "scripts/verify_foundation_003.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)


class Foundation003Tests(unittest.TestCase):
    def test_static_task_checks_pass(self) -> None:
        checks = VERIFY.run_checks(
            verify_worktree=False,
            allow_external_main_dirty=False,
            run_external=False,
            owner_runtime=False,
        )
        self.assertEqual([item.status for item in checks], ["PASS"] * len(checks))

    def test_run_is_exactly_one_task(self) -> None:
        self.assertEqual(VERIFY.TASK_ID, "TSK.x2n.foundation.003")
        self.assertEqual(VERIFY.RUN_ID, "RUN-X2N-S01-F003")
        self.assertEqual(VERIFY.TASK_BASE_COMMIT, "ae17e377090ef3bc1123d2512cda0daef9efe1cb")
        self.assertEqual(VERIFY.FINAL_COMMIT, "84731bde18495ab20af005bc70d59d5ce73cbe93")
        self.assertEqual(VERIFY.ORIGIN_CUTOFF, "a444a3e9e8ee3246f2f1763aceb55d519795e30b")
        self.assertEqual(VERIFY.ALLOWED_CHANGED_PREFIXES, ("evidence/data/",))

    def test_schema_snapshot_is_exact_and_contains_no_private_fields(self) -> None:
        snapshot = json.loads(VERIFY.SCHEMA_SNAPSHOT.read_text(encoding="utf-8"))
        self.assertEqual(snapshot["database_schema_version"], 2)
        self.assertEqual(snapshot["object_counts"], {"index": 9, "table": 17, "trigger": 15})
        rendered = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("media_cdn_url TEXT", rendered)
        self.assertNotIn("cookie TEXT", rendered)
        self.assertNotIn("token TEXT", rendered)

    def test_store_fixture_meets_thresholds_and_is_synthetic(self) -> None:
        fixture = json.loads(VERIFY.FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(fixture["case_count"], 10_182)
        self.assertEqual((fixture["idempotency_items"], fixture["idempotency_runs"]), (80, 2))
        self.assertEqual(fixture["concurrent_duplicate_messages"], 100)
        self.assertEqual(fixture["scale_records"], 10_000)
        self.assertTrue(fixture["synthetic_only"])
        for field in (
            "real_accounts",
            "contains_credentials",
            "contains_private_content",
            "contains_media_urls",
            "contains_local_absolute_paths",
        ):
            self.assertFalse(fixture[field])

    def test_external_environment_is_minimal_and_has_no_repository_credentials(self) -> None:
        env = VERIFY._isolated_env(Path("isolated-home"))
        self.assertEqual(env["UV_KEYRING_PROVIDER"], "disabled")
        self.assertEqual(env["UV_NO_CONFIG"], "1")
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertNotIn("GH_TOKEN", env)
        self.assertNotIn("X2N_DATA_ROOT", env)
        self.assertNotIn("X2N_DOWNLOAD_DESTINATION", env)

    def test_acceptance_scope_does_not_claim_downstream_products(self) -> None:
        state = json.loads(VERIFY.TASK_STATE.read_text(encoding="utf-8"))
        self.assertEqual(state["current_stage_gate"], "pass")
        self.assertEqual(state["current_stage_remote_upload"], "authorized_after_g1_pass")
        self.assertIn("markdown_notion_owner_alpha_downstream_not_run", state["acceptance_status"]["ACC.x2n.data.002"])
        self.assertIn("release_disaster_recovery_downstream_not_run", state["acceptance_status"]["ACC.x2n.data.004"])
        for field in ("real_account_execution", "real_sink_execution", "platform_calls", "notion_calls"):
            self.assertEqual(state[field], "not_run")


if __name__ == "__main__":
    unittest.main()
