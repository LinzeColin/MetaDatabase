from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify_stage_0_review", PROJECT_ROOT / "scripts/verify_stage_0_review.py")
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)


class Stage0ReviewTests(unittest.TestCase):
    def test_core_checks_pass(self) -> None:
        checks = VERIFY.run_core_checks()
        self.assertEqual([check.status for check in checks], ["PASS"] * len(checks))

    def test_single_task_rule_and_review_exception_are_exact(self) -> None:
        taskpack = VERIFY._load_yaml(VERIFY.TASKPACK)
        policy = taskpack["execution_policy"]
        self.assertTrue(policy["single_task_focus"])
        self.assertEqual(policy["max_tasks_per_run"], 1)
        project = VERIFY._load_json(VERIFY.PROJECT_FACT)
        self.assertEqual(project["run_maximum"], "one_task")
        self.assertEqual(project["stage_review_run_kind"], "no_new_dag_task")

    def test_pending_owner_action_can_never_be_g0_pass(self) -> None:
        gate = VERIFY._load_json(VERIFY.GATE_STATE)
        VERIFY.validate_gate_payload(gate)
        pending = copy.deepcopy(gate)
        pending.update({
            "review_id": VERIFY.REVIEW_ID,
            "run_id": VERIFY.REVIEW_RUN_ID,
            "gate_status": "blocked_owner_action",
            "gate_decision": "fail_closed",
            "blocking_followups": [{
                "id": VERIFY.INCIDENT_ID,
                "scope": "before_g0_pass",
                "status": "owner_action_pending",
                "required_resolution": "rotate_or_reauthenticate_or_prove_expiry",
            }],
            "stage_1_authorized": False,
            "remote_upload": "forbidden_until_g0_pass",
        })
        VERIFY.validate_gate_payload(pending)
        invalid = copy.deepcopy(pending)
        invalid["gate_status"] = "pass"
        invalid["gate_decision"] = "pass"
        invalid["stage_1_authorized"] = True
        invalid["remote_upload"] = "authorized_after_g0_pass"
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY.validate_gate_payload(invalid)

    def test_recovery_attestation_only_authorizes_review_resume(self) -> None:
        schema = VERIFY._load_json(VERIFY.RECOVERY_SCHEMA)
        properties = schema["properties"]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), set(properties))
        self.assertFalse(properties["g0_pass_granted"]["const"])
        self.assertFalse(properties["stage_1_authorized"]["const"])
        self.assertFalse(properties["remote_upload_authorized"]["const"])
        path_contract = VERIFY._load_json(VERIFY.PATH_CONTRACT)
        self.assertIn(
            "runtime/owner_recovery_attestation.local.json",
            path_contract["allowed_private_contract_files"],
        )

    def test_all_six_platforms_remain_disabled(self) -> None:
        registry = VERIFY._load_json_at(VERIFY.REVIEW_FINAL_COMMIT, VERIFY.PLATFORM_SCOPE)
        self.assertEqual(tuple(item["id"] for item in registry["platforms"]), VERIFY.PLATFORMS)
        self.assertTrue(all(item["policy_state"] == "unknown_disabled" for item in registry["platforms"]))
        self.assertFalse(registry["implementation_started"])
        self.assertFalse(registry["real_platform_calls"])

    def test_restricted_competitors_remain_non_executable(self) -> None:
        registry = VERIFY._load_json(VERIFY.COMPETITOR)
        self.assertEqual(registry["actual_runtime_dependencies"], [])
        self.assertEqual(registry["code_copies"], 0)
        boundary = registry["restricted_research_boundary"]
        for key in ("product_adapter_allowed", "installation_allowed", "execution_allowed", "output_ingest_allowed", "runtime_dependency_allowed", "vendoring_allowed"):
            self.assertFalse(boundary[key])

    def test_phase_receipts_remain_historical_and_fail_closed(self) -> None:
        check = VERIFY.validate_phase_receipts()
        self.assertEqual(check.status, "PASS")
        self.assertEqual(check.details["files"], 20)
        self.assertEqual(check.details["downstream_product_oracles"], "NOT_RUN")

    def test_review_evidence_is_complete_and_blocked(self) -> None:
        check = VERIFY.validate_review_evidence()
        self.assertEqual(check.status, "PASS")
        self.assertEqual(check.details["g0"], "BLOCKED_OWNER_ACTION")
        self.assertFalse(check.details["stage_1_authorized"])

    def test_external_main_isolation_is_aggregate_only(self) -> None:
        details = VERIFY._evaluate_main_isolation(["another-project/example.txt"], True)
        self.assertEqual(details["external_main_dirty_paths"], 1)
        self.assertEqual(details["project_overlap_paths"], 0)
        self.assertNotIn("another-project", json.dumps(details))
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY._evaluate_main_isolation(["xhs-douyin-2notion/README.md"], True)


if __name__ == "__main__":
    unittest.main()
