import json
import re
import tempfile
import unittest
from pathlib import Path

from signal_lattice.receipts import add_self_hash, verify_self_hash
from signal_lattice.state_machine import validate_state


class TaskpackSealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]

    def test_owner_override_is_valid_only_when_explicitly_bound(self):
        state = json.loads((self.root / "CANONICAL_STATE.json").read_text(encoding="utf-8"))
        result = validate_state(state, "0.0.0.1.39")
        self.assertEqual(result.state, "PASS", result.findings)
        self.assertEqual(result.current_phase, "SEALED_TASKPACK")
        gate = state["owner_gate"]
        self.assertTrue(gate["eligible"])
        self.assertTrue(gate["owner_override_authorized"])
        self.assertEqual(gate["owner_override_scope"], "TASKPACK_SEAL_ONLY_NOT_RELEASE_PASS")

    def test_owner_receipt_and_taskpack_seal_are_self_hashed(self):
        for rel in (
            "evidence/owner_gate/taskpack_owner_approval.json",
            "evidence/owner_gate/taskpack_seal.json",
        ):
            data = json.loads((self.root / rel).read_text(encoding="utf-8"))
            self.assertTrue(verify_self_hash(data), rel)
        seal = json.loads((self.root / "evidence/owner_gate/taskpack_seal.json").read_text(encoding="utf-8"))
        self.assertEqual(seal["scope"], "SEALED_DEVELOPMENT_TASKPACK_ONLY")
        self.assertFalse(seal["formal_release_pass_claimed"])
        self.assertFalse(seal["live_action_enabled"])
        self.assertEqual(seal["runtime_agent_dependency"], 0)
        self.assertEqual(seal["runtime_llm_token_budget"], 0)
        if seal.get("version") == "0.0.0.1.39":
            self.assertRegex(seal["embedded_stock_skill_payload_sha256"], re.compile(r"^[0-9a-f]{64}$"))

    def test_residual_tasks_are_environment_bound_only(self):
        data = json.loads((self.root / "machine/facts/residual_environment_tasks.json").read_text(encoding="utf-8"))
        self.assertGreater(len(data["tasks"]), 0)
        self.assertTrue(all(row["environment_bound"] is True for row in data["tasks"]))
        self.assertTrue(all(row.get("environment_bound_reason") for row in data["tasks"]))


    def test_subject_identity_excludes_mutable_evidence(self):
        subject = json.loads((self.root / "SUBJECT_LOCK.json").read_text(encoding="utf-8"))
        paths = {row["path"] for row in subject["files"]}
        self.assertFalse(any(path.startswith("evidence/") for path in paths))

    def test_self_hash_helper(self):
        payload = add_self_hash({"state": "PASS"})
        self.assertTrue(verify_self_hash(payload))


if __name__ == "__main__":
    unittest.main()
