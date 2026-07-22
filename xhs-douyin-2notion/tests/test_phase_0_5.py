from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify_phase_0_5", PROJECT_ROOT / "scripts/verify_phase_0_5.py")
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)


class Phase05Tests(unittest.TestCase):
    def test_core_checks_pass(self) -> None:
        checks = VERIFY.run_core_checks()
        self.assertEqual([check.status for check in checks], ["PASS"] * len(checks))

    def test_six_platforms_are_exact_and_disabled(self) -> None:
        registry = VERIFY._load_json_at(VERIFY.PHASE_FINAL_COMMIT, VERIFY.PLATFORMS)
        self.assertEqual({item["id"] for item in registry["platforms"]}, VERIFY.PLATFORM_IDS)
        self.assertTrue(all(item["policy_state"] == "unknown_disabled" for item in registry["platforms"]))
        self.assertFalse(registry["implementation_started"])
        self.assertFalse(registry["real_platform_calls"])

    def test_competitor_is_clean_room_only(self) -> None:
        registry = json.loads((PROJECT_ROOT / "machine/facts/competitor_registry.json").read_text(encoding="utf-8"))
        item = registry["competitors"][0]
        self.assertFalse(item["license"]["commercial_use_allowed"])
        self.assertFalse(item["license"]["code_copy_allowed_in_x2n"])
        self.assertEqual(item["integration"]["vendored_files"], 0)
        self.assertEqual(registry["actual_runtime_dependencies"], [])
        boundary = registry["restricted_research_boundary"]
        self.assertEqual(boundary["sources"], ["ShilongLee-Crawler", "MediaCrawler"])
        self.assertFalse(boundary["product_adapter_allowed"])
        self.assertFalse(boundary["installation_allowed"])
        self.assertFalse(boundary["execution_allowed"])
        self.assertFalse(boundary["output_ingest_allowed"])

    def test_synthetic_fixture_has_attack_coverage(self) -> None:
        fixture = json.loads((PROJECT_ROOT / "machine/fixtures/stage_0_governance_cases.json").read_text(encoding="utf-8"))
        self.assertEqual(len(fixture["cases"]), 50)
        categories = {item["category"] for item in fixture["cases"]}
        self.assertTrue({"platform", "network", "media", "ipc", "privacy", "ai", "license", "release"}.issubset(categories))
        self.assertTrue(fixture["synthetic_only"])
        self.assertFalse(fixture["real_accounts"])
        by_id = {item["id"]: item for item in fixture["cases"]}
        self.assertEqual(by_id["GOV-049"]["expected_decision"], "incident_delete_clone_rotate_or_prove_expiry")
        self.assertEqual(by_id["GOV-050"]["expected_decision"], "reject_product_adapter")

    def test_owner_taxonomy_and_media_are_fail_closed_in_schema(self) -> None:
        schema = json.loads((PROJECT_ROOT / "machine/schemas/owner_input_contract.schema.json").read_text(encoding="utf-8"))
        taxonomy = schema["properties"]["taxonomy"]["properties"]
        media = schema["properties"]["media_retention"]["properties"]
        self.assertFalse(taxonomy["ai_may_create_top_level"]["const"])
        self.assertFalse(media["persist_platform_cdn_urls"]["const"])
        self.assertFalse(media["persist_raw_media"]["const"])
        self.assertEqual(media["failure_max_hours"]["maximum"], 24)

    def test_stage_and_external_execution_remain_not_run(self) -> None:
        state = VERIFY._load_json_at(VERIFY.STAGE_1_REVIEW_COMMIT, VERIFY.TASK_STATE)
        self.assertEqual(state["tasks"]["TSK.x2n.discovery.005"], "pass")
        self.assertIn(
            state["review_id"],
            {"STG.X2N.0.REVIEW", "STG.X2N.0.REVIEW.RESUME", "STG.X2N.1.REVIEW"},
        )
        self.assertIn(state["stage_gate"], {"blocked_owner_action", "pass"})
        if state.get("current_stage_gate") == "pass":
            expected_upload = "authorized_after_g1_pass"
        else:
            expected_upload = "authorized_after_g0_pass" if state["stage_gate"] == "pass" else "forbidden_until_g0_pass"
        self.assertEqual(state["remote_upload"], expected_upload)
        self.assertEqual(state["stage_1_authorized"], state["stage_gate"] == "pass")
        self.assertEqual(state["acceptance_status"]["ACC.x2n.media.003"], "design_fixture_pass_downstream_not_run")
        self.assertEqual(state["blocking_followups"][0]["scope"], "before_g0_pass")
        expected_followup = "resolved" if state["stage_gate"] == "pass" else "owner_action_pending"
        self.assertEqual(state["blocking_followups"][0]["status"], expected_followup)

    def test_worktree_isolation_defaults_strict_and_override_is_aggregate_only(self) -> None:
        strict = VERIFY._evaluate_main_isolation([], False)
        self.assertEqual(strict["isolation_mode"], "strict_main_clean")
        self.assertTrue(strict["main_worktree_clean"])

        isolated = VERIFY._evaluate_main_isolation(["EEI/example.txt"], True)
        self.assertEqual(isolated["isolation_mode"], "external_main_dirty_zero_project_overlap")
        self.assertEqual(isolated["external_main_dirty_paths"], 1)
        self.assertEqual(isolated["project_overlap_paths"], 0)
        self.assertNotIn("EEI/example.txt", json.dumps(isolated))

    def test_worktree_isolation_fails_closed_without_override_or_on_overlap(self) -> None:
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY._evaluate_main_isolation(["EEI/example.txt"], False)
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY._evaluate_main_isolation(["xhs-douyin-2notion/README.md"], True)
        legacy = "xiao" + "hongshu-douyin-2notion"
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY._evaluate_main_isolation([f"{legacy}/README.md"], True)

    def test_parent_index_exception_allows_only_the_exact_project_rename(self) -> None:
        legacy = "xiao" + "hongshu-douyin-2notion"
        valid = "\n".join([
            "--- a/README.md",
            "+++ b/README.md",
            f"-| {legacy} | stage | description |",
            "+| xhs-douyin-2notion | stage | description |",
        ])
        VERIFY._validate_parent_index_diff(valid)
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY._validate_parent_index_diff(valid + "\n+unexpected")

    def test_transitional_legacy_scope_allows_deletions_only(self) -> None:
        legacy = "xiao" + "hongshu-douyin-2notion"
        allowed, count = VERIFY._scope_status(f"D  {legacy}/README.md\nA  xhs-douyin-2notion/README.md")
        self.assertTrue(allowed)
        self.assertEqual(count, 1)
        denied, _ = VERIFY._scope_status(f"M  {legacy}/README.md")
        self.assertFalse(denied)


if __name__ == "__main__":
    unittest.main()
