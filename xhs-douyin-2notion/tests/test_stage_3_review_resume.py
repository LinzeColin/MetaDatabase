from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_stage_3_review_resume",
    PROJECT_ROOT / "scripts/verify_stage_3_review_resume.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)


class Stage3ReviewResumeTests(unittest.TestCase):
    def test_static_contract_checks_pass_without_external_execution(self) -> None:
        checks = VERIFY.run_checks(
            verify_worktree=False,
            require_evidence=False,
            lane_report=None,
        )
        self.assertEqual([item.status for item in checks], ["PASS"] * len(checks))

    def test_false_g3_pass_or_authorization_is_rejected(self) -> None:
        fact = json.loads(VERIFY.RESUME_FACT.read_text(encoding="utf-8"))
        promoted = copy.deepcopy(fact)
        promoted["decision"]["gate_status"] = "PASS"
        promoted["decision"]["gate_decision"] = "PASS"
        promoted["authorization"]["stage_3_upload"] = True
        promoted["authorization"]["stage_4"] = True
        promoted["authorization"]["deployment"] = True
        with self.assertRaises(VERIFY.ResumeError):
            VERIFY._validate_resume_fact(promoted)

    def test_task010_is_required_and_cannot_be_marked_complete_by_contract(self) -> None:
        taskpack = VERIFY._load_yaml_unique(VERIFY.TASKPACK)
        changed = copy.deepcopy(taskpack)
        task = next(item for item in changed["tasks"] if item["id"] == VERIFY.NEXT_TASK)
        task["status"] = "completed"
        changed["stage_gates"][3]["requires_tasks"].remove(VERIFY.NEXT_TASK)
        with self.assertRaises(VERIFY.ResumeError):
            VERIFY._validate_taskpack_payload(changed)

    def test_stage_4_and_release_cannot_bypass_task010_or_g3(self) -> None:
        taskpack = VERIFY._load_yaml_unique(VERIFY.TASKPACK)
        changed = copy.deepcopy(taskpack)
        changed["execution_policy"]["previous_stage_gate_pass_required"] = False
        stage_4_entry = next(
            item for item in changed["tasks"] if item["id"] == "TSK.x2n.multimodal.001"
        )
        stage_4_entry["depends_on"].remove(VERIFY.NEXT_TASK)
        with self.assertRaises(VERIFY.ResumeError):
            VERIFY._validate_taskpack_payload(changed)

    def test_fixed_wait_prerelease_or_soak_is_rejected(self) -> None:
        fact = json.loads(VERIFY.RESUME_FACT.read_text(encoding="utf-8"))
        changed = copy.deepcopy(fact)
        changed["release_policy"]["pre_release_phases"] = "ALLOWED"
        changed["release_policy"]["fixed_health_observation"] = "30_DAYS"
        changed["release_policy"]["fixed_soak"] = "REQUIRED"
        with self.assertRaises(VERIFY.ResumeError):
            VERIFY._validate_release_payload(changed)

    def test_g6_cannot_be_a_precondition_to_its_own_release_task(self) -> None:
        fact = json.loads(VERIFY.RESUME_FACT.read_text(encoding="utf-8"))
        changed = copy.deepcopy(fact)
        changed["release_policy"]["gate_order"] = [
            "G0_TO_G6_PASS",
            "ASSURANCE_005_DEPLOY_RUN_ONLINE_SMOKE",
        ]
        with self.assertRaises(VERIFY.ResumeError):
            VERIFY._validate_release_payload(changed)

    def test_security_cannot_be_degraded_to_reach_mvp(self) -> None:
        fact = json.loads(VERIFY.RESUME_FACT.read_text(encoding="utf-8"))
        changed = copy.deepcopy(fact)
        changed["release_policy"]["assurance_005_in_task_pre_switch_checks"][2] = (
            "SECURITY_AND_MODEL_ASSURANCE_PASS_OR_EXPLICIT_DEGRADE"
        )
        with self.assertRaises(VERIFY.ResumeError):
            VERIFY._validate_release_payload(changed)

    def test_assurance005_in_task_output_cannot_be_a_start_condition(self) -> None:
        taskpack = VERIFY._load_yaml_unique(VERIFY.TASKPACK)
        changed = copy.deepcopy(taskpack)
        task = next(
            item for item in changed["tasks"]
            if item["id"] == "TSK.x2n.assurance.005"
        )
        task["task_start_conditions"].append("eighty-item owner mvp passes")
        with self.assertRaises(VERIFY.ResumeError):
            VERIFY._validate_taskpack_payload(changed)

    def test_private_database_clone_or_unverified_durability_is_rejected(self) -> None:
        fact = json.loads(VERIFY.RESUME_FACT.read_text(encoding="utf-8"))
        changed = copy.deepcopy(fact)
        changed["data_routing"]["clone"] = "ALLOWED"
        changed["data_routing"]["raw_sqlite_db_upload"] = "ALLOWED"
        changed["data_routing"]["archival_chunk_max_bytes"] = 99614720
        changed["data_routing"]["durability_before_verified_receipt"] = "DURABLE"
        with self.assertRaises(VERIFY.ResumeError):
            VERIFY._validate_data_routing_payload(changed)

    def test_all_sixteen_historical_review_artifacts_are_byte_immutable(self) -> None:
        protected = VERIFY._historical_protected_paths()
        self.assertEqual(len(protected), 16)
        for path in protected:
            historical = VERIFY._blob_at(VERIFY.BASE_COMMIT, path)
            self.assertEqual(path.read_bytes(), historical, path.as_posix())
        self.assertEqual(
            VERIFY._sha256(VERIFY.HISTORICAL_GATE_FACT),
            VERIFY.HISTORICAL_GATE_SHA256,
        )

    def test_terminal_states_are_exact_and_fail_closed(self) -> None:
        fact = json.loads(VERIFY.RESUME_FACT.read_text(encoding="utf-8"))
        terminals = fact["capability_terminal_contract"]
        self.assertEqual(
            terminals["allowed"],
            ["READY_FOR_MVP_ACTIVATION", "DISABLED_EXTERNAL_GATE"],
        )
        self.assertFalse(terminals["disabled_feature_flag"])
        self.assertEqual(terminals["disabled_platform_calls"], 0)
        self.assertFalse(terminals["disabled_live_support_claim"])
        self.assertEqual(terminals["scope_ids"], VERIFY.EXPECTED_SCOPE_IDS)
        self.assertEqual(
            terminals["reason_precedence"],
            VERIFY.EXPECTED_CAPABILITY_REASON_PRECEDENCE,
        )
        self.assertEqual(
            terminals["runtime_authority"],
            "SQLITE_CAPABILITY_GATE_OUTCOME_DERIVED_SNAPSHOT",
        )

    def test_capability_runtime_authority_or_reason_precedence_drift_is_rejected(self) -> None:
        fact = json.loads(VERIFY.RESUME_FACT.read_text(encoding="utf-8"))
        changed = copy.deepcopy(fact)
        changed["capability_terminal_contract"]["runtime_authority"] = "MULTIPLE_REGISTRIES"
        changed["capability_terminal_contract"]["reason_precedence"].reverse()
        with self.assertRaises(VERIFY.ResumeError):
            VERIFY._validate_resume_fact(changed)

    def test_capability_snapshot_cardinality_cannot_hide_technical_veto(self) -> None:
        fact = json.loads(VERIFY.RESUME_FACT.read_text(encoding="utf-8"))
        changed = copy.deepcopy(fact)
        changed["capability_terminal_contract"]["persistence"] = (
            "ONE_DERIVED_RUNTIME_OUTCOME_ROW_PER_SCOPE"
        )
        changed["capability_terminal_contract"]["technical_reason_semantics"] = (
            "TECHNICAL_CAN_SETTLE_AS_DISABLED_EXTERNAL_GATE"
        )
        with self.assertRaises(VERIFY.ResumeError):
            VERIFY._validate_resume_fact(changed)

    def test_task010_must_make_all_eight_scopes_typed_and_representable(self) -> None:
        taskpack = VERIFY._load_yaml_unique(VERIFY.TASKPACK)
        changed = copy.deepcopy(taskpack)
        task = next(item for item in changed["tasks"] if item["id"] == VERIFY.NEXT_TASK)
        task["outputs"] = [
            output for output in task["outputs"]
            if "versioned discriminated GET_CAPABILITIES result" not in output
            and "saved_current allowed in START_SYNC only" not in output
        ]
        with self.assertRaises(VERIFY.ResumeError):
            VERIFY._validate_taskpack_payload(changed)

    def test_assurance005_owned_acceptance_set_is_exact(self) -> None:
        taskpack = VERIFY._load_yaml_unique(VERIFY.TASKPACK)
        changed = copy.deepcopy(taskpack)
        changed["execution_policy"]["assurance_005_owned_in_task_acceptance_ids"].remove(
            "ACC.x2n.data.002"
        )
        release_task = next(
            item
            for item in changed["tasks"]
            if item["id"] == "TSK.x2n.assurance.005"
        )
        release_task["acceptance_ids"].remove("ACC.x2n.data.002")
        with self.assertRaises(VERIFY.ResumeError):
            VERIFY._validate_taskpack_payload(changed)

    def test_time_machine_target_cannot_be_claimed_implemented_in_resume(self) -> None:
        fact = json.loads(VERIFY.RESUME_FACT.read_text(encoding="utf-8"))
        changed = copy.deepcopy(fact)
        changed["data_routing"]["os_backup_policy"] = (
            "ENTIRE_X2N_DATA_ROOT_EXCLUDED_AND_VERIFIED"
        )
        with self.assertRaises(VERIFY.ResumeError):
            VERIFY._validate_data_routing_payload(changed)

    def test_changed_scope_is_an_exact_allowlist_subset(self) -> None:
        allowed = next(iter(VERIFY.RESUME_CHANGED_PATH_ALLOWLIST))
        self.assertEqual(VERIFY._validate_changed_scope([allowed]), [allowed])
        with self.assertRaises(VERIFY.ResumeError):
            VERIFY._validate_changed_scope(
                ["xhs-douyin-2notion/packages/companion/src/unrelated.py"]
            )

    def test_lane_report_cannot_vacuously_pass_without_exact_gates(self) -> None:
        baseline = {
            "lane": "fast",
            "status": "PASS",
            "blocking_repetitions": 1,
            "blocking_commands": 9,
            "blocking_executions": 9,
            "blocking_failures": 0,
            "flaky_blocking_tests": 0,
            "silent_blocking_skips": 0,
            "explicit_nonblocking_skips": 3,
            "blocking_results": [
                {
                    "gate": gate,
                    "label": f"{gate}_r1",
                    "repetition": 1,
                    "blocking": True,
                    "status": "PASS",
                }
                for gate in VERIFY.EXPECTED_FAST_LANE_GATES
            ],
            "platform_calls": 0,
            "model_calls": 0,
            "real_accounts": 0,
            "remote_github_actions": "NOT_RUN_LOCAL_BASELINE",
            "stage_gate_evaluation": "NOT_PERFORMED_BY_SOFTWARE_LANE",
            "toolchain": {
                "actual": {
                    "coverage": "7.15.2",
                    "node": "24.18.0",
                    "npm": "11.16.0",
                    "python": "3.12.13",
                    "pyyaml": "6.0.3",
                    "ruff": "0.15.22",
                    "uv": "0.11.28",
                }
            },
        }
        VERIFY._validate_lane_report_payload(baseline)
        with self.subTest("empty"):
            changed = copy.deepcopy(baseline)
            changed["blocking_results"] = []
            with self.assertRaises(VERIFY.ResumeError):
                VERIFY._validate_lane_report_payload(changed)
        with self.subTest("duplicate"):
            changed = copy.deepcopy(baseline)
            changed["blocking_results"][-1] = copy.deepcopy(
                changed["blocking_results"][0]
            )
            with self.assertRaises(VERIFY.ResumeError):
                VERIFY._validate_lane_report_payload(changed)
        with self.subTest("remote"):
            changed = copy.deepcopy(baseline)
            changed["remote_github_actions"] = "PASS"
            with self.assertRaises(VERIFY.ResumeError):
                VERIFY._validate_lane_report_payload(changed)

    def test_external_actions_are_explicitly_process_attestation(self) -> None:
        fact = json.loads(VERIFY.RESUME_FACT.read_text(encoding="utf-8"))
        self.assertEqual(
            fact["external_execution"]["evidence_class"],
            "PROCESS_ATTESTATION_NOT_INDEPENDENTLY_OBSERVED_BY_OFFLINE_VERIFIER",
        )
        decision = json.loads(VERIFY.DECISION_EVIDENCE.read_text(encoding="utf-8"))
        self.assertEqual(
            decision["verification_scope"]["external_execution"],
            "PROCESS_ATTESTATION_NOT_INDEPENDENTLY_OBSERVED",
        )
        self.assertNotIn("real_platform_calls", decision)

    def test_active_product_contract_has_no_prerelease_label_or_version(self) -> None:
        product_text = "\n".join(
            path.read_text(encoding="utf-8") for path in VERIFY.ACTIVE_PRODUCT_DOCS
        )
        self.assertIsNone(VERIFY.re.search(r"\b(?:alpha|beta)\b", product_text, flags=VERIFY.re.IGNORECASE))
        self.assertIsNone(VERIFY.re.search(r"v0\.0\.0\.1-[a-z0-9]", product_text, flags=VERIFY.re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
