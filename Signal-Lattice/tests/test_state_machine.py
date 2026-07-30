import json, unittest
from pathlib import Path
from signal_lattice.constants import VERSION
from signal_lattice.state_machine import PHASES, can_transition, load_state, validate_state

class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]

    def test_canonical_state_passes(self):
        result = validate_state(load_state(self.root / "CANONICAL_STATE.json"), VERSION)
        self.assertEqual(result.state, "PASS", result.findings)
        self.assertEqual(result.current_phase, "SEALED_TASKPACK")

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
