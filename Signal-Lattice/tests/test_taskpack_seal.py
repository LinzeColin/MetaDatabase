import json
import tempfile
import unittest
from pathlib import Path

from signal_lattice.constants import VERSION
from signal_lattice.receipts import add_self_hash, verify_self_hash
from signal_lattice.state_machine import validate_state


class TaskpackSealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]

    def test_owner_override_is_valid_only_when_explicitly_bound(self):
        """Owner override 只有在同时绑定正确 scope 与回执时才成立——双向验证。

        旧版本断言的是「override 已被授权」，那是在锁定某次项目进度，而不是在测同名的
        不变量；版本号也硬编码成 0.0.0.1.41，随发布线前进必然失效。现在测的是条件本身：
        声称 override 却没绑对 scope / 回执 → 必须报错；绑对了 → 不得报 override 类错。
        """
        version = VERSION
        base = json.loads((self.root / "CANONICAL_STATE.json").read_text(encoding="utf-8"))
        self.assertEqual(validate_state(base, version).state, "PASS", validate_state(base, version).findings)

        bound = json.loads(json.dumps(base))
        bound["owner_gate"].update({
            "owner_override_authorized": True,
            "owner_override_scope": "TASKPACK_SEAL_ONLY_NOT_RELEASE_PASS",
            "owner_approval_receipt": "evidence/owner_gate/taskpack_owner_approval.json",
            "eligible": True,
        })
        findings = validate_state(bound, version).findings
        self.assertNotIn("OWNER_GATE_OVERRIDE_SCOPE_INVALID", findings)
        self.assertNotIn("OWNER_GATE_OVERRIDE_RECEIPT_INVALID", findings)
        self.assertNotIn("OWNER_GATE_ELIGIBILITY_MISMATCH", findings)

        for field, value, expected in (
            ("owner_override_scope", "ANY_SCOPE_I_LIKE", "OWNER_GATE_OVERRIDE_SCOPE_INVALID"),
            ("owner_approval_receipt", "evidence/owner_gate/some_other_file.json", "OWNER_GATE_OVERRIDE_RECEIPT_INVALID"),
        ):
            unbound = json.loads(json.dumps(bound))
            unbound["owner_gate"][field] = value
            self.assertIn(expected, validate_state(unbound, version).findings, field)

    def test_shipped_state_does_not_claim_an_unearned_owner_gate(self):
        """仓库里这份状态文件不得声称拿到了实际不存在的 Owner 批准。"""
        gate = json.loads((self.root / "CANONICAL_STATE.json").read_text(encoding="utf-8"))["owner_gate"]
        rounds = gate.get("qualifying_no_change_rounds", 0)
        earned = bool(rounds >= 2) or gate.get("owner_override_authorized") is True
        self.assertEqual(bool(gate["eligible"]), earned)

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
