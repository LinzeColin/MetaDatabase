from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify_phase_0_1", PROJECT_ROOT / "scripts/verify_phase_0_1.py")
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)


class Phase01Tests(unittest.TestCase):
    def test_core_checks_pass(self) -> None:
        checks = VERIFY.run_core_checks()
        self.assertEqual([check.status for check in checks], ["PASS"] * len(checks))

    def test_phase_scope_is_exact(self) -> None:
        self.assertEqual(
            VERIFY.PHASE_TASKS,
            (
                "TSK.x2n.discovery.001",
                "TSK.x2n.discovery.002",
                "TSK.x2n.discovery.003",
            ),
        )

    def test_downstream_gates_fail_closed(self) -> None:
        state = json.loads(VERIFY._run_git(
            ["show", "2a81db2dd36638b00175ec6226462b37905d4705:xhs-douyin-2notion/machine/facts/task_state.json"],
            VERIFY.PROJECT_ROOT.parent,
        ))
        self.assertIn(state["stage_gate"], {"blocked_owner_action", "pass"})
        if state["stage_gate"] == "blocked_owner_action":
            self.assertFalse(state["next_phase_authorized"])
            self.assertFalse(state["stage_1_authorized"])
            self.assertEqual(state["remote_upload"], "forbidden_until_g0_pass")
        else:
            self.assertTrue(state["next_phase_authorized"])
            self.assertTrue(state["stage_1_authorized"])
            expected_upload = (
                "authorized_after_g1_pass"
                if state.get("current_stage_gate") == "pass"
                else "authorized_after_g0_pass"
            )
            self.assertEqual(state["remote_upload"], expected_upload)
        self.assertIn(
            state["downstream_acceptances"]["ACC.x2n.gov.002"],
            {
                "downstream_not_run",
                "pass_current_source_build_candidate_scope_owner_release_downstream_not_run",
            },
        )
        for acceptance_id in ("ACC.x2n.media.001", "ACC.x2n.ops.002"):
            self.assertEqual(state["downstream_acceptances"][acceptance_id], "downstream_not_run")

    def test_private_root_when_explicitly_supplied(self) -> None:
        value = os.environ.get("X2N_DATA_ROOT")
        if not value:
            self.skipTest("owner-private root is intentionally absent in public CI")
        check = VERIFY.validate_local_root(Path(value))
        self.assertEqual(check.status, "PASS")


if __name__ == "__main__":
    unittest.main()
