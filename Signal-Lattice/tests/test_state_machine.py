import json, unittest
from pathlib import Path
from signal_lattice.constants import VERSION
from signal_lattice.state_machine import PHASES, can_transition, load_state, validate_state

class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]

    def test_canonical_state_passes(self):
        """CANONICAL_STATE.json 必须在当前版本下通过状态机校验，且阶段与 Owner 闸门一致。

        这里不锁定某一个具体阶段：阶段是项目进度，会随重建推进而变。要守的不变量是
        「文件描述的阶段合法」与「未取得 Owner 闸门就不得自称已封包或更后」。
        """
        state = load_state(self.root / "CANONICAL_STATE.json")
        result = validate_state(state, VERSION)
        self.assertEqual(result.state, "PASS", result.findings)
        self.assertIn(result.current_phase, PHASES)
        gate = state["owner_gate"]
        earned = bool(gate.get("qualifying_no_change_rounds", 0) >= 2) or gate.get("owner_override_authorized") is True
        if PHASES.index(result.current_phase) >= PHASES.index("SEALED_TASKPACK"):
            self.assertTrue(earned, "已到 SEALED_TASKPACK 或更后阶段，但 Owner 闸门未取得")
        self.assertEqual(bool(gate["eligible"]), earned)

    def test_transition_is_strictly_sequential(self):
        self.assertTrue(can_transition("REMEDIATION", "BUILDER_READINESS"))
        self.assertFalse(can_transition("REMEDIATION", "OWNER_GATE"))
        self.assertFalse(can_transition("OWNER_GATE", "REMEDIATION"))

    def test_owner_gate_cannot_be_claimed_early(self):
        state = load_state(self.root / "CANONICAL_STATE.json")
        state["owner_gate"].pop("owner_override_authorized", None)
        state["owner_gate"].pop("owner_override_scope", None)
        state["owner_gate"].pop("owner_approval_receipt", None)
        state["owner_gate"]["qualifying_no_change_rounds"] = 0
        state["owner_gate"]["eligible"] = True
        result = validate_state(state, VERSION)
        self.assertIn("OWNER_GATE_ELIGIBILITY_MISMATCH", result.findings)
